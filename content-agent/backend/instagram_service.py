from __future__ import annotations

import requests
from sqlalchemy.orm import Session

from backend.db_models import MediaAsset, SocialAccount
from backend.security import decrypt_text, encrypt_text
from config.settings import settings

GRAPH_BASE = "https://graph.facebook.com/v25.0"


def _get_instagram_profile(account_id: str, access_token: str) -> dict:
    resp = requests.get(
        f"{GRAPH_BASE}/{account_id}",
        params={"fields": "id,username", "access_token": access_token},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Instagram profile lookup failed: {resp.status_code} {resp.text[:250]}")
    return resp.json()


def connect_instagram_from_settings(db: Session, user_id: str) -> SocialAccount:
    account_id = (settings.instagram_business_account_id or "").strip()
    token = (settings.instagram_access_token or "").strip()
    if not account_id or not token:
        raise RuntimeError("INSTAGRAM_BUSINESS_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN are required")

    profile = _get_instagram_profile(account_id, token)
    account_name = str(profile.get("username") or "Instagram Business").strip()

    row = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "instagram")
        .first()
    )
    if row:
        row.account_id = account_id
        row.account_name = account_name
        row.access_token_enc = encrypt_text(token)
    else:
        row = SocialAccount(
            user_id=user_id,
            platform="instagram",
            account_id=account_id,
            account_name=account_name,
            access_token_enc=encrypt_text(token),
            refresh_token_enc="",
            expires_at=None,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _create_media_container(account_id: str, token: str, image_url: str, caption: str) -> str:
    resp = requests.post(
        f"{GRAPH_BASE}/{account_id}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": token,
        },
        timeout=45,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Instagram media create failed: {resp.status_code} {resp.text[:320]}")
    container_id = str(resp.json().get("id") or "").strip()
    if not container_id:
        raise RuntimeError("Instagram media container id missing")
    return container_id


def _publish_media_container(account_id: str, token: str, container_id: str) -> str:
    resp = requests.post(
        f"{GRAPH_BASE}/{account_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=45,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Instagram publish failed: {resp.status_code} {resp.text[:320]}")
    post_id = str(resp.json().get("id") or "").strip()
    if not post_id:
        raise RuntimeError("Instagram publish id missing")
    return post_id


def publish_to_instagram(
    db: Session,
    user_id: str,
    content: str,
    media_items: list[MediaAsset] | None = None,
) -> dict:
    account = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "instagram")
        .first()
    )
    if not account:
        raise RuntimeError("Instagram account is not connected")

    image_item = next((x for x in (media_items or []) if x.mime_type.startswith("image/")), None)
    if not image_item:
        raise RuntimeError("Instagram publish requires at least one image")
    if not image_item.file_url:
        raise RuntimeError("Instagram publish requires a signed media URL")

    token = decrypt_text(account.access_token_enc)
    container_id = _create_media_container(account.account_id, token, image_item.file_url, content)
    external_post_id = _publish_media_container(account.account_id, token, container_id)
    return {"external_post_id": external_post_id}
