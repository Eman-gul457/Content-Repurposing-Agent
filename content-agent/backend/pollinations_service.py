from __future__ import annotations

import random
from urllib.parse import quote


def build_pollinations_image_url(prompt: str, width: int = 1280, height: int = 720) -> str:
    safe_prompt = quote((prompt or "modern social media design")[:350], safe="")
    seed = random.randint(1000, 999999)
    return (
        f"https://image.pollinations.ai/prompt/{safe_prompt}"
        f"?width={width}&height={height}&seed={seed}&nologo=true&model=flux"
    )
