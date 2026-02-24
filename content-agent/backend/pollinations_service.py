from __future__ import annotations

import random
from urllib.parse import quote


def build_pollinations_image_url(prompt: str, width: int = 1280, height: int = 720) -> str:
    _ = width, height, random.randint(1000, 999999)
    safe_prompt = quote((prompt or "modern social media design")[:350], safe="")
    # Use Pollinations preview page URL. It is currently more reliable than image.pollinations.ai direct endpoint.
    return f"https://pollinations.ai/p/{safe_prompt}"
