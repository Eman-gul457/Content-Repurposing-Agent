from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from backend.db_models import OAuthState, SocialAccount
from backend.security import encrypt_text
from config.settings import settings

CANVA_AUTH_URL = "https://www.canva.com/api/oauth/authorize"
CANVA_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"


def _state_serializer() -> URLSafeTimedSerializer:
    if not settings.state_signing_secret:
        raise RuntimeError("STATE_SIGNING_SECRET is required")
    return URLSafeTimedSerializer(settings.state_signing_secret, salt="canva-oauth-state")


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def create_canva_authorization_url(db: Session, user_id: str) -> str:
    if not settings.canva_client_id or not settings.canva_redirect_uri:
        raise RuntimeError("CANVA_CLIENT_ID and CANVA_REDIRECT_URI are required")

    verifier = secrets.token_urlsafe(64)[:96]
    state = _state_serializer().dumps({"user_id": user_id, "provider": "canva", "verifier": verifier})

    db.add(OAuthState(user_id=user_id, provider="canva", state_token=state))
    db.commit()

    params = {
        "response_type": "code",
        "client_id": settings.canva_client_id,
        "redirect_uri": settings.canva_redirect_uri,
        "scope": settings.canva_scopes,
        "state": state,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    return f"{CANVA_AUTH_URL}?{urlencode(params)}"


def handle_canva_callback(db: Session, code: str, state: str) -> str:
    if not settings.canva_client_id or not settings.canva_client_secret or not settings.canva_redirect_uri:
        raise RuntimeError("Canva OAuth credentials are incomplete")

    state_row = db.query(OAuthState).filter(OAuthState.state_token == state).first()
    if not state_row:
        raise RuntimeError("Invalid OAuth state")

    try:
        payload = _state_serializer().loads(state, max_age=900)
    except SignatureExpired as exc:
        raise RuntimeError("OAuth state expired") from exc
    except BadSignature as exc:
        raise RuntimeError("Invalid OAuth signature") from exc

    user_id = payload.get("user_id")
    verifier = payload.get("verifier")
    if not user_id or user_id != state_row.user_id:
        raise RuntimeError("OAuth user mismatch")
    if not verifier:
        raise RuntimeError("OAuth verifier missing")

    token_resp = requests.post(
        CANVA_TOKEN_URL,
        auth=(settings.canva_client_id, settings.canva_client_secret),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.canva_redirect_uri,
            "code_verifier": verifier,
        },
        timeout=30,
    )
    if token_resp.status_code >= 400:
        raise RuntimeError(f"Canva token exchange failed: {token_resp.status_code} {token_resp.text[:220]}")

    token_data = token_resp.json()
    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = int(token_data.get("expires_in", 3600))
    if not access_token:
        raise RuntimeError("Canva access token missing")
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    existing = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "canva")
        .first()
    )
    if existing:
        existing.account_id = token_data.get("id_token", "")[:120] or "canva-account"
        existing.account_name = "Canva Connected"
        existing.access_token_enc = encrypt_text(access_token)
        existing.refresh_token_enc = encrypt_text(refresh_token) if refresh_token else ""
        existing.expires_at = expires_at
    else:
        db.add(
            SocialAccount(
                user_id=user_id,
                platform="canva",
                account_id=token_data.get("id_token", "")[:120] or "canva-account",
                account_name="Canva Connected",
                access_token_enc=encrypt_text(access_token),
                refresh_token_enc=encrypt_text(refresh_token) if refresh_token else "",
                expires_at=expires_at,
            )
        )

    db.delete(state_row)
    db.commit()
    return user_id
