from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import Session

from config.settings import settings
from backend.db_models import MediaAsset, OAuthState, SocialAccount
from backend.media_service import download_media_bytes
from backend.security import decrypt_text, encrypt_text


LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_UGC_POST_URL = "https://api.linkedin.com/v2/ugcPosts"
LINKEDIN_ASSETS_URL = "https://api.linkedin.com/v2/assets?action=registerUpload"


def _state_serializer() -> URLSafeTimedSerializer:
    if not settings.state_signing_secret:
        raise RuntimeError("STATE_SIGNING_SECRET is required")
    return URLSafeTimedSerializer(settings.state_signing_secret, salt="linkedin-oauth-state")


def create_linkedin_authorization_url(db: Session, user_id: str) -> str:
    if not settings.linkedin_client_id or not settings.linkedin_redirect_uri:
        raise RuntimeError("LINKEDIN_CLIENT_ID and LINKEDIN_REDIRECT_URI are required")

    state = _state_serializer().dumps({"user_id": user_id, "provider": "linkedin"})
    db.add(OAuthState(user_id=user_id, provider="linkedin", state_token=state))
    db.commit()

    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": settings.linkedin_redirect_uri,
        "state": state,
        "scope": "openid profile w_member_social",
    }
    return f"{LINKEDIN_AUTH_URL}?{urlencode(params)}"


def _exchange_code_for_token(code: str) -> dict:
    response = requests.post(
        LINKEDIN_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.linkedin_redirect_uri,
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _fetch_userinfo(access_token: str) -> dict:
    response = requests.get(
        LINKEDIN_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def handle_linkedin_callback(db: Session, code: str, state: str) -> str:
    state_row = db.query(OAuthState).filter(OAuthState.state_token == state).first()
    if not state_row:
        raise RuntimeError("Invalid OAuth state")

    try:
        payload = _state_serializer().loads(state, max_age=600)
    except SignatureExpired as exc:
        raise RuntimeError("OAuth state expired") from exc
    except BadSignature as exc:
        raise RuntimeError("Invalid OAuth signature") from exc

    user_id = payload.get("user_id")
    if not user_id or user_id != state_row.user_id:
        raise RuntimeError("OAuth user mismatch")

    token_data = _exchange_code_for_token(code)
    access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)

    user_info = _fetch_userinfo(access_token)
    account_id = user_info.get("sub")
    if not account_id:
        raise RuntimeError("LinkedIn user id missing")

    account_name = user_info.get("name", "LinkedIn User")
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    existing = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "linkedin")
        .first()
    )

    if existing:
        existing.account_id = account_id
        existing.account_name = account_name
        existing.access_token_enc = encrypt_text(access_token)
        existing.expires_at = expires_at
    else:
        db.add(
            SocialAccount(
                user_id=user_id,
                platform="linkedin",
                account_id=account_id,
                account_name=account_name,
                access_token_enc=encrypt_text(access_token),
                expires_at=expires_at,
            )
        )

    db.delete(state_row)
    db.commit()
    return user_id


def _register_linkedin_asset(token: str, owner_urn: str, mime_type: str) -> tuple[str, str]:
    recipe = "urn:li:digitalmediaRecipe:feedshare-image"
    if mime_type == "application/pdf":
        recipe = "urn:li:digitalmediaRecipe:feedshare-document"

    payload = {
        "registerUploadRequest": {
            "recipes": [recipe],
            "owner": owner_urn,
            "serviceRelationships": [{"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}],
        }
    }
    resp = requests.post(
        LINKEDIN_ASSETS_URL,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json().get("value", {})
    asset = data.get("asset", "")
    upload_url = (
        data.get("uploadMechanism", {})
        .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
        .get("uploadUrl", "")
    )
    if not asset or not upload_url:
        raise RuntimeError("LinkedIn asset register response incomplete")
    return asset, upload_url


def _upload_linkedin_binary(upload_url: str, token: str, mime_type: str, content: bytes) -> None:
    upload_resp = requests.put(
        upload_url,
        data=content,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": mime_type,
        },
        timeout=60,
    )
    if upload_resp.status_code >= 400:
        raise RuntimeError(f"LinkedIn binary upload failed: {upload_resp.status_code} {upload_resp.text[:200]}")


def _ensure_linkedin_media_assets(token: str, owner_urn: str, media_items: list[MediaAsset]) -> None:
    for item in media_items:
        if item.platform_asset_id:
            continue

        last_error = ""
        for _ in range(3):
            try:
                asset, upload_url = _register_linkedin_asset(token, owner_urn, item.mime_type)
                blob = download_media_bytes(item.storage_path)
                _upload_linkedin_binary(upload_url, token, item.mime_type, blob)
                item.platform_asset_id = asset
                item.upload_status = "uploaded"
                item.last_error = ""
                break
            except Exception as exc:
                last_error = str(exc)
                item.upload_status = "failed"
                item.last_error = last_error

        if not item.platform_asset_id:
            raise RuntimeError(f"Media upload failed for {item.file_name}: {last_error}")


def publish_to_linkedin(db: Session, user_id: str, content: str, media_items: list[MediaAsset] | None = None) -> dict:
    account = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "linkedin")
        .first()
    )
    if not account:
        raise RuntimeError("LinkedIn account is not connected")

    token = decrypt_text(account.access_token_enc)
    author = f"urn:li:person:{account.account_id}"
    media_items = media_items or []
    _ensure_linkedin_media_assets(token, author, media_items)

    share_media_category = "NONE"
    share_media = []
    if media_items:
        if any(item.mime_type == "application/pdf" for item in media_items):
            share_media_category = "NONE"
        else:
            share_media_category = "IMAGE"
            for item in media_items:
                share_media.append(
                    {
                        "status": "READY",
                        "media": item.platform_asset_id,
                        "title": {"text": item.file_name},
                    }
                )

    payload = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": content},
                "shareMediaCategory": share_media_category,
                "media": share_media,
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    response = requests.post(
        LINKEDIN_UGC_POST_URL,
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(f"LinkedIn publish failed: {response.status_code} {response.text[:300]}")

    db.commit()

    return {
        "external_post_id": response.headers.get("x-restli-id", ""),
        "status_code": response.status_code,
    }
