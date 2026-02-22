import requests
from jose import jwt
from fastapi import Header, HTTPException

from config.settings import settings

_cached_jwks: dict | None = None


def _jwks_url() -> str:
    if settings.supabase_jwks_url:
        return settings.supabase_jwks_url
    if settings.supabase_url:
        return f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    raise RuntimeError("SUPABASE_URL or SUPABASE_JWKS_URL is required")


def _get_jwks() -> dict:
    global _cached_jwks
    if _cached_jwks is not None:
        return _cached_jwks

    response = requests.get(_jwks_url(), timeout=20)
    response.raise_for_status()
    _cached_jwks = response.json()
    return _cached_jwks


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return authorization.replace("Bearer ", "", 1).strip()


def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    token = _extract_bearer_token(authorization)

    unverified = jwt.get_unverified_header(token)
    kid = unverified.get("kid")
    keys = _get_jwks().get("keys", [])
    key = next((k for k in keys if k.get("kid") == kid), None)
    if not key:
        raise HTTPException(status_code=401, detail="Invalid token key")

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[key.get("alg", "RS256")],
            options={"verify_aud": False},
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return user_id