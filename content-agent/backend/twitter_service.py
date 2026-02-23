import base64
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from backend.db_models import MediaAsset, OAuthState, SocialAccount
from backend.media_service import download_media_bytes
from backend.security import decrypt_text, encrypt_text
from config.settings import settings

TWITTER_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
TWITTER_TOKEN_URL = "https://api.x.com/2/oauth2/token"
TWITTER_USERINFO_URL = "https://api.x.com/2/users/me"
TWITTER_TWEET_CREATE_URL = "https://api.x.com/2/tweets"
TWITTER_MEDIA_UPLOAD_URL = "https://api.x.com/2/media/upload"
TWITTER_SCOPE = "tweet.read tweet.write users.read"
TWITTER_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/pjpeg"}
TWITTER_MAX_IMAGE_BYTES = 5 * 1024 * 1024


class TwitterUnauthorizedError(RuntimeError):
    pass


def _state_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.state_signing_secret, salt="twitter-oauth-state")


def _basic_auth_header() -> str:
    raw = f"{settings.twitter_client_id}:{settings.twitter_client_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("utf-8")


def _generate_code_verifier() -> str:
    # RFC 7636: verifier length must be 43-128 chars
    return secrets.token_urlsafe(64)[:96]


def _code_challenge_s256(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def create_twitter_authorization_url(db: Session, user_id: str) -> str:
    if not settings.twitter_client_id or not settings.twitter_redirect_uri:
        raise RuntimeError("Twitter OAuth settings are missing")

    code_verifier = _generate_code_verifier()
    code_challenge = _code_challenge_s256(code_verifier)
    state = _state_serializer().dumps(
        {"user_id": user_id, "provider": "twitter", "code_verifier": code_verifier}
    )
    db.add(OAuthState(user_id=user_id, provider="twitter", state_token=state))
    db.commit()

    params = {
        "response_type": "code",
        "client_id": settings.twitter_client_id,
        "redirect_uri": settings.twitter_redirect_uri,
        "scope": TWITTER_SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{TWITTER_AUTH_URL}?{urlencode(params)}"


def _exchange_code_for_token(code: str, code_verifier: str) -> dict:
    headers = {
        "Authorization": _basic_auth_header(),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.twitter_redirect_uri,
        "client_id": settings.twitter_client_id,
        "code_verifier": code_verifier,
    }
    resp = requests.post(TWITTER_TOKEN_URL, headers=headers, data=data, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"Twitter token exchange failed ({resp.status_code}): {resp.text}")
    return resp.json()


def _refresh_access_token(refresh_token: str) -> dict:
    headers = {
        "Authorization": _basic_auth_header(),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.twitter_client_id,
    }
    resp = requests.post(TWITTER_TOKEN_URL, headers=headers, data=data, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"Twitter refresh failed ({resp.status_code}): {resp.text}")
    return resp.json()


def _fetch_twitter_profile(access_token: str) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(TWITTER_USERINFO_URL, headers=headers, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"Twitter profile fetch failed ({resp.status_code}): {resp.text}")
    payload = resp.json().get("data", {})
    account_id = str(payload.get("id", "")).strip()
    account_name = str(payload.get("username") or payload.get("name") or "").strip()
    if not account_id:
        raise RuntimeError("Twitter profile response missing account id")
    return account_id, account_name


def handle_twitter_callback(db: Session, code: str, state: str) -> str:
    try:
        payload = _state_serializer().loads(state, max_age=900)
    except SignatureExpired as exc:
        raise RuntimeError("Twitter auth state expired; please try again") from exc
    except BadSignature as exc:
        raise RuntimeError("Invalid Twitter auth state") from exc

    user_id = payload.get("user_id", "")
    provider = payload.get("provider", "")
    code_verifier = payload.get("code_verifier", "")
    if not user_id or provider != "twitter":
        raise RuntimeError("Invalid Twitter auth state payload")
    if not code_verifier:
        raise RuntimeError("Invalid Twitter auth state: missing PKCE verifier")

    state_row = db.query(OAuthState).filter(OAuthState.state_token == state, OAuthState.provider == "twitter").first()
    if not state_row:
        raise RuntimeError("Twitter auth state not found or already used")
    db.delete(state_row)
    db.commit()

    token_data = _exchange_code_for_token(code, code_verifier)
    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = int(token_data.get("expires_in") or 0)
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in > 0 else None

    if not access_token:
        raise RuntimeError("Twitter token exchange returned no access token")

    account_id, account_name = _fetch_twitter_profile(access_token)

    existing = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "twitter")
        .first()
    )
    if existing:
        existing.account_id = account_id
        existing.account_name = account_name
        existing.access_token_enc = encrypt_text(access_token)
        existing.refresh_token_enc = encrypt_text(refresh_token) if refresh_token else ""
        existing.expires_at = expires_at
    else:
        db.add(
            SocialAccount(
                user_id=user_id,
                platform="twitter",
                account_id=account_id,
                account_name=account_name,
                access_token_enc=encrypt_text(access_token),
                refresh_token_enc=encrypt_text(refresh_token) if refresh_token else "",
                expires_at=expires_at,
            )
        )

    db.commit()
    return account_name


def _post_tweet(access_token: str, content: str, media_ids: list[str] | None = None) -> requests.Response:
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload: dict = {"text": content}
    if media_ids:
        payload["media"] = {"media_ids": media_ids}
    return requests.post(TWITTER_TWEET_CREATE_URL, headers=headers, json=payload, timeout=30)


def _wait_for_media_ready(access_token: str, media_id: str, check_after_secs: int = 1) -> None:
    headers = {"Authorization": f"Bearer {access_token}"}
    wait_seconds = max(1, min(check_after_secs, 4))
    for _ in range(8):
        time.sleep(wait_seconds)
        resp = requests.get(TWITTER_MEDIA_UPLOAD_URL, headers=headers, params={"id": media_id}, timeout=30)
        if resp.status_code == 401:
            raise TwitterUnauthorizedError("Twitter token expired")
        if resp.status_code >= 400:
            raise RuntimeError(f"Twitter media status failed ({resp.status_code}): {resp.text}")
        data = resp.json().get("data", {})
        info = data.get("processing_info") or {}
        state = str(info.get("state", "succeeded")).lower()
        if state == "succeeded":
            return
        if state == "failed":
            raise RuntimeError(f"Twitter media processing failed: {resp.text}")
        wait_seconds = max(1, min(int(info.get("check_after_secs") or wait_seconds), 5))

    raise RuntimeError("Twitter media processing timed out")


def _upload_twitter_media(access_token: str, item: MediaAsset) -> str:
    if item.mime_type not in TWITTER_IMAGE_MIME_TYPES:
        raise RuntimeError(f"Twitter supports image media only. Unsupported type: {item.mime_type}")

    blob = download_media_bytes(item.storage_path)
    if len(blob) > TWITTER_MAX_IMAGE_BYTES:
        raise RuntimeError(f"Twitter image too large ({item.file_name}). Max size is 5MB")

    payload = {
        "media": base64.b64encode(blob).decode("utf-8"),
        "media_category": "tweet_image",
        "media_type": item.mime_type,
        "shared": False,
    }
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    last_error = ""
    for attempt in range(1, 4):
        resp = requests.post(TWITTER_MEDIA_UPLOAD_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code == 401:
            raise TwitterUnauthorizedError("Twitter token expired")
        if resp.status_code < 400:
            body = resp.json()
            data = body.get("data", {})
            media_id = str(data.get("id", "")).strip()
            if not media_id:
                raise RuntimeError(f"Twitter media upload returned no media id: {resp.text}")
            processing_info = data.get("processing_info") or {}
            if processing_info and str(processing_info.get("state", "succeeded")).lower() != "succeeded":
                _wait_for_media_ready(
                    access_token=access_token,
                    media_id=media_id,
                    check_after_secs=int(processing_info.get("check_after_secs") or 1),
                )
            return media_id

        last_error = f"Twitter media upload failed ({resp.status_code}): {resp.text}"
        if resp.status_code < 500 or attempt == 3:
            break
        time.sleep(attempt)

    raise RuntimeError(last_error or "Twitter media upload failed")


def _ensure_twitter_media_ids(db: Session, access_token: str, media_items: list[MediaAsset]) -> list[str]:
    if not media_items:
        return []

    if len(media_items) > 4:
        raise RuntimeError("Twitter supports up to 4 images per post")

    media_ids: list[str] = []
    for item in media_items:
        media_id = _upload_twitter_media(access_token, item)
        item.platform_asset_id = media_id
        item.upload_status = "twitter_asset_ready"
        item.last_error = ""
        media_ids.append(media_id)

    db.commit()
    return media_ids


def _refresh_twitter_account_tokens(db: Session, account: SocialAccount) -> str:
    if not account.refresh_token_enc:
        raise RuntimeError("Twitter access token expired and no refresh token is available")

    refresh_data = _refresh_access_token(decrypt_text(account.refresh_token_enc))
    access_token = refresh_data.get("access_token", "")
    if not access_token:
        raise RuntimeError("Twitter token refresh returned no access token")

    account.access_token_enc = encrypt_text(access_token)
    refresh_token = refresh_data.get("refresh_token")
    if refresh_token:
        account.refresh_token_enc = encrypt_text(refresh_token)

    expires_in = int(refresh_data.get("expires_in") or 0)
    account.expires_at = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in > 0 else None
    db.commit()
    return access_token


def publish_to_twitter(
    db: Session,
    user_id: str,
    content: str,
    media_items: list[MediaAsset] | None = None,
) -> dict:
    account = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "twitter")
        .first()
    )
    if not account:
        raise RuntimeError("Twitter account is not connected")

    access_token = decrypt_text(account.access_token_enc)
    media_ids: list[str] = []

    try:
        if media_items:
            media_ids = _ensure_twitter_media_ids(db, access_token, media_items)
        response = _post_tweet(access_token, content, media_ids=media_ids)
        if response.status_code == 401:
            raise TwitterUnauthorizedError("Twitter token expired")
    except TwitterUnauthorizedError:
        access_token = _refresh_twitter_account_tokens(db, account)
        media_ids = _ensure_twitter_media_ids(db, access_token, media_items or [])
        response = _post_tweet(access_token, content, media_ids=media_ids)

    if response.status_code >= 400:
        raise RuntimeError(f"Twitter publish failed ({response.status_code}): {response.text}")

    body = response.json()
    external_post_id = str(body.get("data", {}).get("id", "")).strip()
    return {"external_post_id": external_post_id}
