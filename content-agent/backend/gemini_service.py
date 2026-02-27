from __future__ import annotations

import base64
from typing import Any

import requests

from config.settings import settings


def _generate_content_url() -> str:
    model = (settings.gemini_image_model or "").strip()
    key = (settings.gemini_api_key or "").strip()
    if not model or not key:
        raise RuntimeError("GEMINI_API_KEY and GEMINI_IMAGE_MODEL are required")
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


def _extract_inline_image(payload: dict[str, Any]) -> tuple[bytes, str] | None:
    candidates = payload.get("candidates") or []
    for candidate in candidates:
        parts = ((candidate or {}).get("content") or {}).get("parts") or []
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data") or {}
            data_b64 = inline.get("data")
            if not data_b64:
                continue
            mime_type = inline.get("mimeType") or inline.get("mime_type") or "image/png"
            try:
                return base64.b64decode(data_b64), mime_type
            except Exception:
                continue
    return None


def generate_image(prompt: str, width: int, height: int, *, strict: bool = False) -> tuple[bytes, str] | None:
    if not (settings.gemini_api_key or "").strip():
        if strict:
            raise RuntimeError("Gemini API key missing")
        return None

    safe_prompt = (
        f"{prompt.strip()}\n\n"
        f"Canvas size target: {width}x{height}. "
        "Return one clean social-media-ready visual image."
    )
    payload = {
        "contents": [{"parts": [{"text": safe_prompt[:4000]}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    response = requests.post(
        _generate_content_url(),
        json=payload,
        timeout=90,
    )
    if response.status_code >= 400:
        if strict:
            raise RuntimeError(f"Gemini image generation failed: {response.status_code} {response.text[:400]}")
        return None
    data = response.json()
    result = _extract_inline_image(data)
    if not result and strict:
        raise RuntimeError("Gemini returned no image bytes for this request")
    return result
