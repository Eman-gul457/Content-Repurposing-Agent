import base64
from datetime import datetime
from pathlib import Path

import requests
from sqlalchemy.orm import Session

from backend.db_models import GeneratedPost, MediaAsset
from config.settings import settings

ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "application/pdf",
}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def _supabase_headers(content_type: str | None = None) -> dict[str, str]:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for media uploads")

    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _ensure_bucket() -> None:
    bucket = settings.supabase_storage_bucket
    url = f"{settings.supabase_url}/storage/v1/bucket/{bucket}"
    r = requests.get(url, headers=_supabase_headers(), timeout=30)
    if r.status_code == 200:
        return

    create = requests.post(
        f"{settings.supabase_url}/storage/v1/bucket",
        headers=_supabase_headers("application/json"),
        json={"id": bucket, "name": bucket, "public": False},
        timeout=30,
    )
    if create.status_code not in (200, 201, 409):
        raise RuntimeError(f"Failed to create storage bucket: {create.status_code} {create.text[:200]}")


def _generate_signed_url(storage_path: str, expires_in: int = 3600) -> str:
    bucket = settings.supabase_storage_bucket
    sign = requests.post(
        f"{settings.supabase_url}/storage/v1/object/sign/{bucket}/{storage_path}",
        headers=_supabase_headers("application/json"),
        json={"expiresIn": expires_in},
        timeout=30,
    )
    sign.raise_for_status()
    signed = sign.json().get("signedURL", "")
    if not signed:
        return ""
    return f"{settings.supabase_url}/storage/v1{signed}"


def upload_media_base64(db: Session, user_id: str, post_id: int, file_name: str, mime_type: str, content_base64: str) -> MediaAsset:
    if mime_type not in ALLOWED_MIME_TYPES:
        raise RuntimeError("Only PNG, JPG/JPEG, and PDF are allowed")

    post = db.query(GeneratedPost).filter(GeneratedPost.id == post_id, GeneratedPost.user_id == user_id).first()
    if not post:
        raise RuntimeError("Post not found")

    if ";base64," in content_base64:
        content_base64 = content_base64.split(";base64,", 1)[1]

    file_bytes = base64.b64decode(content_base64)
    if len(file_bytes) == 0:
        raise RuntimeError("Uploaded file is empty")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise RuntimeError("File too large (max 8MB)")

    safe_name = Path(file_name).name.replace(" ", "_")
    storage_path = f"{user_id}/{post_id}/{int(datetime.utcnow().timestamp())}_{safe_name}"

    _ensure_bucket()

    upload = requests.post(
        f"{settings.supabase_url}/storage/v1/object/{settings.supabase_storage_bucket}/{storage_path}",
        headers={**_supabase_headers(mime_type), "x-upsert": "true"},
        data=file_bytes,
        timeout=60,
    )

    if upload.status_code not in (200, 201):
        raise RuntimeError(f"Storage upload failed: {upload.status_code} {upload.text[:200]}")

    signed_url = _generate_signed_url(storage_path)

    row = MediaAsset(
        user_id=user_id,
        post_id=post_id,
        platform=post.platform,
        file_name=safe_name,
        mime_type=mime_type,
        file_size=len(file_bytes),
        storage_path=storage_path,
        file_url=signed_url,
        upload_status="uploaded",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_post_media(db: Session, user_id: str, post_id: int) -> list[MediaAsset]:
    return (
        db.query(MediaAsset)
        .filter(MediaAsset.user_id == user_id, MediaAsset.post_id == post_id)
        .order_by(MediaAsset.created_at.asc())
        .all()
    )


def refresh_media_signed_urls(db: Session, media_items: list[MediaAsset]) -> None:
    changed = False
    for item in media_items:
        url = _generate_signed_url(item.storage_path)
        if url and url != item.file_url:
            item.file_url = url
            changed = True
    if changed:
        db.commit()


def download_media_bytes(storage_path: str) -> bytes:
    r = requests.get(
        f"{settings.supabase_url}/storage/v1/object/{settings.supabase_storage_bucket}/{storage_path}",
        headers=_supabase_headers(),
        timeout=60,
    )
    r.raise_for_status()
    return r.content