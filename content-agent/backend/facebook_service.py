from __future__ import annotations

import requests
from sqlalchemy.orm import Session

from backend.db_models import MediaAsset, SocialAccount
from backend.media_service import download_media_bytes
from backend.security import decrypt_text, encrypt_text
from config.settings import settings

GRAPH_BASE = "https://graph.facebook.com/v25.0"


def _get_page_profile(page_id: str, page_access_token: str) -> dict:
    resp = requests.get(
        f"{GRAPH_BASE}/{page_id}",
        params={"fields": "id,name", "access_token": page_access_token},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Facebook page lookup failed: {resp.status_code} {resp.text[:250]}")
    return resp.json()


def connect_facebook_from_settings(db: Session, user_id: str) -> SocialAccount:
    page_id = (settings.facebook_page_id or "").strip()
    page_token = (settings.facebook_page_access_token or "").strip()
    if not page_id or not page_token:
        raise RuntimeError("FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN are required")

    profile = _get_page_profile(page_id, page_token)
    account_name = str(profile.get("name") or "Facebook Page").strip()

    row = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "facebook")
        .first()
    )
    if row:
        row.account_id = page_id
        row.account_name = account_name
        row.access_token_enc = encrypt_text(page_token)
    else:
        row = SocialAccount(
            user_id=user_id,
            platform="facebook",
            account_id=page_id,
            account_name=account_name,
            access_token_enc=encrypt_text(page_token),
            refresh_token_enc="",
            expires_at=None,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _publish_text_post(page_id: str, token: str, content: str) -> dict:
    resp = requests.post(
        f"{GRAPH_BASE}/{page_id}/feed",
        data={"message": content, "access_token": token},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Facebook publish failed: {resp.status_code} {resp.text[:300]}")
    return resp.json()


def _publish_photo_post(page_id: str, token: str, content: str, media_item: MediaAsset) -> dict:
    if not media_item.mime_type.startswith("image/"):
        raise RuntimeError("Facebook publish currently supports image media only")
    blob = download_media_bytes(media_item.storage_path)
    files = {"source": (media_item.file_name, blob, media_item.mime_type)}
    data = {"caption": content, "access_token": token}
    resp = requests.post(
        f"{GRAPH_BASE}/{page_id}/photos",
        data=data,
        files=files,
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Facebook media publish failed: {resp.status_code} {resp.text[:300]}")
    return resp.json()


def publish_to_facebook(
    db: Session,
    user_id: str,
    content: str,
    media_items: list[MediaAsset] | None = None,
) -> dict:
    account = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "facebook")
        .first()
    )
    if not account:
        raise RuntimeError("Facebook account is not connected")

    token = decrypt_text(account.access_token_enc)
    page_id = account.account_id
    items = media_items or []
    image_item = next((x for x in items if x.mime_type.startswith("image/")), None)

    payload = (
        _publish_photo_post(page_id, token, content, image_item) if image_item else _publish_text_post(page_id, token, content)
    )
    external_post_id = str(payload.get("post_id") or payload.get("id") or "").strip()
    return {"external_post_id": external_post_id}
