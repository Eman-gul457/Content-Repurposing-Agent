from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from datetime import datetime
from typing import Any

import requests
from sqlalchemy.orm import Session

from backend.db_models import ApprovalRequest, GeneratedPost, PostStatus
from config.settings import settings

WHATSAPP_API_VERSION = "v22.0"
APPROVAL_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 3


def _get_signing_secret() -> bytes:
    secret = (settings.state_signing_secret or "").strip()
    if not secret:
        raise RuntimeError("STATE_SIGNING_SECRET is required for WhatsApp approval links")
    return secret.encode("utf-8")


def _b64_url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64_url_decode(raw: str) -> bytes:
    padded = raw + "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def _sign_payload(payload_b64: str) -> str:
    signature = hmac.new(_get_signing_secret(), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    return _b64_url_encode(signature)


def create_approval_token(post_id: int, user_id: str) -> str:
    payload = {
        "post_id": post_id,
        "user_id": user_id,
        "exp": int(time.time()) + APPROVAL_TOKEN_TTL_SECONDS,
    }
    payload_b64 = _b64_url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _sign_payload(payload_b64)
    return f"{payload_b64}.{sig}"


def parse_approval_token(token: str) -> dict[str, Any]:
    if "." not in token:
        raise RuntimeError("Invalid approval token")
    payload_b64, sent_sig = token.split(".", 1)
    expected = _sign_payload(payload_b64)
    if not hmac.compare_digest(sent_sig, expected):
        raise RuntimeError("Invalid approval token signature")
    payload = json.loads(_b64_url_decode(payload_b64).decode("utf-8"))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise RuntimeError("Approval link expired")
    return payload


def _normalize_phone(number: str) -> str:
    digits = re.sub(r"[^\d]", "", number or "")
    return digits


def get_recipients() -> list[str]:
    raw = settings.whatsapp_recipients or ""
    recipients: list[str] = []
    for part in raw.split(","):
        normalized = _normalize_phone(part.strip())
        if normalized:
            recipients.append(normalized)
    return recipients


def _wa_headers() -> dict[str, str]:
    token = (settings.whatsapp_access_token or "").strip()
    if not token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN is not configured")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _wa_messages_url() -> str:
    phone_id = (settings.whatsapp_phone_number_id or "").strip()
    if not phone_id:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID is not configured")
    return f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{phone_id}/messages"


def _send_template_message(to_number: str) -> None:
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": settings.whatsapp_template_name,
            "language": {"code": settings.whatsapp_template_lang},
        },
    }
    resp = requests.post(_wa_messages_url(), headers=_wa_headers(), json=payload, timeout=30)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"WhatsApp template send failed: {resp.status_code} {resp.text[:220]}")


def _send_text_message(to_number: str, text: str) -> None:
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    resp = requests.post(_wa_messages_url(), headers=_wa_headers(), json=payload, timeout=30)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"WhatsApp text send failed: {resp.status_code} {resp.text[:220]}")


def _build_action_links(post_id: int, user_id: str) -> tuple[str, str]:
    frontend = (settings.frontend_url or "").rstrip("/")
    if not frontend:
        raise RuntimeError("FRONTEND_URL is required for WhatsApp approval links")
    token = create_approval_token(post_id=post_id, user_id=user_id)
    approve = f"{frontend}/?wa_approval_token={token}&wa_action=approve"
    reject = f"{frontend}/?wa_approval_token={token}&wa_action=reject"
    return approve, reject


def request_whatsapp_approval(db: Session, post: GeneratedPost) -> dict[str, Any]:
    recipients = get_recipients()
    if not recipients:
        raise RuntimeError("WHATSAPP_RECIPIENT_NUMBERS is empty")
    approve_url, reject_url = _build_action_links(post.id, post.user_id)
    text = (post.edited_text or "").strip() or (post.generated_text or "").strip()
    snippet = re.sub(r"\s+", " ", text)[:280]
    if len(text) > 280:
        snippet += "..."

    body = (
        "AI Agent approval request\n"
        f"Platform: {post.platform.upper()}\n"
        f"Draft: {snippet}\n\n"
        f"Approve: {approve_url}\n"
        f"Reject: {reject_url}"
    )

    sent = 0
    for recipient in recipients:
        _send_template_message(recipient)
        _send_text_message(recipient, body)
        sent += 1

    approval = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.user_id == post.user_id, ApprovalRequest.post_id == post.id)
        .first()
    )
    if not approval:
        approval = ApprovalRequest(
            user_id=post.user_id,
            post_id=post.id,
            status="pending",
            requested_at=datetime.utcnow(),
        )
        db.add(approval)
    else:
        approval.status = "pending"
        approval.requested_at = datetime.utcnow()
        approval.resolved_at = None
        approval.resolution_note = ""
    db.commit()

    return {"sent_to": sent, "approve_url": approve_url, "reject_url": reject_url}


def resolve_whatsapp_approval(db: Session, token: str, action: str) -> dict[str, Any]:
    payload = parse_approval_token(token)
    post_id = int(payload["post_id"])
    user_id = str(payload["user_id"])

    post = db.query(GeneratedPost).filter(GeneratedPost.id == post_id, GeneratedPost.user_id == user_id).first()
    if not post:
        raise RuntimeError("Post not found for approval token")

    approval = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.user_id == user_id, ApprovalRequest.post_id == post.id)
        .first()
    )
    if not approval:
        approval = ApprovalRequest(user_id=user_id, post_id=post.id, status="pending", requested_at=datetime.utcnow())
        db.add(approval)

    now = datetime.utcnow()
    action_norm = (action or "").strip().lower()
    if action_norm == "approve":
        post.status = PostStatus.approved.value
        approval.status = "approved"
        approval.resolution_note = "Approved via WhatsApp link"
        message = "Draft approved successfully."
    elif action_norm == "reject":
        post.status = PostStatus.rejected.value
        approval.status = "rejected"
        approval.resolution_note = "Rejected via WhatsApp link"
        message = "Draft rejected successfully."
    else:
        raise RuntimeError("Invalid action")

    approval.resolved_at = now
    post.updated_at = now
    db.commit()
    db.refresh(post)
    return {"status": post.status, "message": message, "post_id": post.id}


def verify_webhook(mode: str | None, verify_token: str | None, challenge: str | None) -> str:
    if mode != "subscribe":
        raise RuntimeError("Invalid webhook mode")
    expected = (settings.whatsapp_verify_token or "").strip()
    if not expected:
        raise RuntimeError("WHATSAPP_VERIFY_TOKEN is not configured")
    if (verify_token or "") != expected:
        raise RuntimeError("Webhook verify token mismatch")
    if not challenge:
        raise RuntimeError("Webhook challenge missing")
    return challenge
