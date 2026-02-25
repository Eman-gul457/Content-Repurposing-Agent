from __future__ import annotations

import html
import hashlib
import random
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
from sqlalchemy.orm import Session

from backend.db_models import ContentPlan
from config.settings import settings

DEFAULT_IMAGE_SIZE = (1080, 1080)
PLAN_IMAGE_EXPIRES_SECONDS = 60 * 60 * 24 * 30
PLATFORM_DIMENSIONS = {
    "linkedin": (1200, 627),
    "twitter": (1600, 900),
    "facebook": (1200, 628),
    "instagram": (1080, 1350),
    "blog_summary": (1080, 1080),
}
STYLE_PRESETS = [
    {
        "bg_1": "#0b1220",
        "bg_2": "#1f2b50",
        "panel": "rgba(255,255,255,0.05)",
        "line": "#4f46e5",
        "tag_1": "#22d3ee",
        "tag_2": "#6366f1",
        "title": "#e2e8f0",
        "sub": "#a5b4fc",
        "brand": "#67e8f9",
    },
    {
        "bg_1": "#081913",
        "bg_2": "#0f5132",
        "panel": "rgba(255,255,255,0.05)",
        "line": "#0f766e",
        "tag_1": "#10b981",
        "tag_2": "#14b8a6",
        "title": "#ecfeff",
        "sub": "#99f6e4",
        "brand": "#2dd4bf",
    },
    {
        "bg_1": "#1b1028",
        "bg_2": "#552190",
        "panel": "rgba(255,255,255,0.05)",
        "line": "#8b5cf6",
        "tag_1": "#a855f7",
        "tag_2": "#ec4899",
        "title": "#f5f3ff",
        "sub": "#ddd6fe",
        "brand": "#c4b5fd",
    },
    {
        "bg_1": "#1a1207",
        "bg_2": "#6b3d06",
        "panel": "rgba(255,255,255,0.05)",
        "line": "#f59e0b",
        "tag_1": "#f97316",
        "tag_2": "#facc15",
        "title": "#fff7ed",
        "sub": "#fed7aa",
        "brand": "#fdba74",
    },
    {
        "bg_1": "#161616",
        "bg_2": "#303030",
        "panel": "rgba(255,255,255,0.06)",
        "line": "#a3a3a3",
        "tag_1": "#4b5563",
        "tag_2": "#9ca3af",
        "title": "#f5f5f5",
        "sub": "#d4d4d8",
        "brand": "#e4e4e7",
    },
]
LAYOUT_VARIANTS = ("classic", "split", "spotlight")


def _supabase_headers(content_type: str | None = None) -> dict[str, str]:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
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


def _generate_signed_url(storage_path: str, expires_in: int = PLAN_IMAGE_EXPIRES_SECONDS) -> str:
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


def _download_pollinations(prompt: str, width: int, height: int) -> tuple[bytes, str] | None:
    safe_prompt = quote(prompt[:400], safe="")
    seed = random.randint(1, 999999)
    urls = [
        f"https://image.pollinations.ai/prompt/{safe_prompt}?width={width}&height={height}&seed={seed}&model=flux&nologo=true",
        f"https://image.pollinations.ai/prompt/{safe_prompt}?width={width}&height={height}&seed={seed}&nologo=true",
    ]
    headers = {"User-Agent": "ContentRepurposingAgent/1.0"}
    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=45)
        except Exception:
            continue
        ctype = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        if response.status_code == 200 and ctype.startswith("image/"):
            return response.content, ctype
    return None


def _pick_dimensions(platform: str) -> tuple[int, int]:
    return PLATFORM_DIMENSIONS.get(platform.lower(), DEFAULT_IMAGE_SIZE)


def _pick_style(seed: str) -> dict[str, str]:
    token = f"{seed}:{random.randint(1, 999999)}"
    h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
    return STYLE_PRESETS[h % len(STYLE_PRESETS)]


def _pick_layout(seed: str) -> str:
    h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)
    return LAYOUT_VARIANTS[h % len(LAYOUT_VARIANTS)]


def _wrap_text(value: str, max_len: int, max_lines: int) -> list[str]:
    words = (value or "").split()
    if not words:
        return []
    lines: list[str] = []
    buf: list[str] = []
    for word in words:
        trial = " ".join(buf + [word]).strip()
        if len(trial) > max_len and buf:
            lines.append(" ".join(buf))
            buf = [word]
        else:
            buf.append(word)
        if len(lines) >= max_lines:
            break
    if len(lines) < max_lines and buf:
        lines.append(" ".join(buf))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if lines and len(lines[-1]) > max_len:
        lines[-1] = lines[-1][: max_len - 3].rstrip() + "..."
    return lines


def _svg_text_block(lines: list[str], x: int, y: int, step: int, size: int, color: str, weight: int = 600) -> str:
    if not lines:
        return ""
    parts = []
    for idx, line in enumerate(lines):
        line_escaped = html.escape(line)
        parts.append(
            f'<text x="{x}" y="{y + (idx * step)}" font-family="Inter, Arial, sans-serif" '
            f'font-weight="{weight}" font-size="{size}" fill="{color}">{line_escaped}</text>'
        )
    return "\n  ".join(parts)


def _fallback_post_svg(
    platform: str,
    theme: str,
    angle: str,
    business_name: str,
    width: int,
    height: int,
    style: dict[str, str],
    layout: str,
) -> bytes:
    title = (theme or f"{platform.upper()} campaign")[:140]
    subtitle = (angle or "AI-generated creative concept")[:180]
    brand = html.escape((business_name or "Your Brand")[:48])
    platform_label = html.escape(platform.upper())
    title_lines = _wrap_text(title, max_len=30, max_lines=3)
    subtitle_lines = _wrap_text(subtitle, max_len=44, max_lines=3)
    title_size = max(30, int(height * 0.078))
    subtitle_size = max(19, int(height * 0.04))
    subtitle_step = max(24, int(subtitle_size * 1.35))
    title_step = max(38, int(title_size * 1.2))
    brand_size = max(22, int(height * 0.038))
    small_size = max(13, int(height * 0.021))
    shape_opacity = 0.14

    if layout == "split":
        title_x = int(width * 0.09)
        title_y = int(height * 0.34)
        subtitle_x = title_x
        subtitle_y = int(height * 0.56)
        panel = (
            f'<rect x="{int(width * 0.06)}" y="{int(height * 0.08)}" width="{int(width * 0.88)}" '
            f'height="{int(height * 0.84)}" rx="{int(height * 0.04)}" fill="{style["panel"]}" '
            f'stroke="{style["line"]}" stroke-opacity="0.55"/>'
            f'<rect x="{int(width * 0.52)}" y="{int(height * 0.10)}" width="{int(width * 0.36)}" '
            f'height="{int(height * 0.34)}" rx="{int(height * 0.03)}" fill="{style["line"]}" fill-opacity="{shape_opacity}"/>'
        )
    elif layout == "spotlight":
        title_x = int(width * 0.08)
        title_y = int(height * 0.42)
        subtitle_x = title_x
        subtitle_y = int(height * 0.62)
        panel = (
            f'<circle cx="{int(width * 0.84)}" cy="{int(height * 0.2)}" r="{int(height * 0.22)}" '
            f'fill="{style["line"]}" fill-opacity="{shape_opacity}"/>'
            f'<rect x="{int(width * 0.06)}" y="{int(height * 0.06)}" width="{int(width * 0.88)}" '
            f'height="{int(height * 0.88)}" rx="{int(height * 0.04)}" fill="{style["panel"]}" '
            f'stroke="{style["line"]}" stroke-opacity="0.55"/>'
        )
    else:
        title_x = int(width * 0.08)
        title_y = int(height * 0.30)
        subtitle_x = title_x
        subtitle_y = int(height * 0.50)
        panel = (
            f'<rect x="{int(width * 0.05)}" y="{int(height * 0.05)}" width="{int(width * 0.90)}" '
            f'height="{int(height * 0.90)}" rx="{int(height * 0.035)}" fill="{style["panel"]}" '
            f'stroke="{style["line"]}" stroke-opacity="0.45"/>'
            f'<path d="M {int(width * 0.52)} {int(height * 0.08)} C {int(width * 0.76)} {int(height * 0.16)}, '
            f'{int(width * 0.76)} {int(height * 0.42)}, {int(width * 0.52)} {int(height * 0.5)}" '
            f'stroke="{style["line"]}" stroke-width="4" stroke-opacity="{shape_opacity}" fill="none"/>'
        )

    tag_x = int(width * 0.07)
    tag_y = int(height * 0.095)
    tag_w = int(width * 0.28)
    tag_h = int(height * 0.065)
    footer_y = int(height * 0.88)
    footer_line_y = int(height * 0.82)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{style["bg_1"]}"/>
      <stop offset="100%" stop-color="{style["bg_2"]}"/>
    </linearGradient>
    <linearGradient id="tag" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{style["tag_1"]}"/>
      <stop offset="100%" stop-color="{style["tag_2"]}"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.85" cy="0.1" r="0.5">
      <stop offset="0%" stop-color="rgba(255,255,255,0.18)"/>
      <stop offset="100%" stop-color="rgba(255,255,255,0)"/>
    </radialGradient>
  </defs>
  <rect width="{width}" height="{height}" fill="url(#bg)"/>
  <circle cx="{int(width * 0.88)}" cy="{int(height * 0.15)}" r="{int(min(width, height) * 0.2)}" fill="url(#glow)"/>
  {panel}
  <rect x="{tag_x}" y="{tag_y}" width="{tag_w}" height="{tag_h}" rx="{int(tag_h * 0.3)}" fill="url(#tag)"/>
  <text x="{tag_x + int(tag_w * 0.08)}" y="{tag_y + int(tag_h * 0.65)}" font-family="Inter, Arial, sans-serif" font-weight="700" font-size="{max(16, int(tag_h * 0.42))}" fill="#ffffff">{platform_label} POST</text>
  {_svg_text_block(title_lines, title_x, title_y, title_step, title_size, style["title"], 800)}
  {_svg_text_block(subtitle_lines, subtitle_x, subtitle_y, subtitle_step, subtitle_size, style["sub"], 500)}
  <rect x="{title_x}" y="{footer_line_y}" width="{int(width * 0.82)}" height="2" fill="{style["line"]}" fill-opacity="0.55"/>
  <text x="{title_x}" y="{footer_y}" font-family="Inter, Arial, sans-serif" font-weight="700" font-size="{brand_size}" fill="{style["brand"]}">{brand}</text>
  <text x="{title_x}" y="{footer_y + int(height * 0.045)}" font-family="Inter, Arial, sans-serif" font-size="{small_size}" fill="#9db0cf">Generated by AI Content SaaS</text>
</svg>"""
    return svg.encode("utf-8")


def _mime_to_ext(mime_type: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
        "image/svg+xml": "svg",
    }.get(mime_type, "bin")


def generate_plan_image(db: Session, user_id: str, plan_id: int, business_name: str = "") -> ContentPlan:
    plan = db.query(ContentPlan).filter(ContentPlan.id == plan_id, ContentPlan.user_id == user_id).first()
    if not plan:
        raise RuntimeError("Plan not found")

    prompt = (plan.image_prompt or f"Social media creative for {plan.platform} {plan.theme}").strip()
    width, height = _pick_dimensions(plan.platform)
    image_bytes = b""
    mime_type = ""

    pol = _download_pollinations(prompt, width, height)
    if pol:
        image_bytes, mime_type = pol
    else:
        seed = f"{plan.id}:{plan.platform}:{plan.theme}:{datetime.utcnow().timestamp()}"
        style = _pick_style(seed)
        layout = _pick_layout(seed)
        image_bytes = _fallback_post_svg(
            plan.platform,
            plan.theme,
            plan.post_angle,
            business_name,
            width,
            height,
            style,
            layout,
        )
        mime_type = "image/svg+xml"

    _ensure_bucket()
    ext = _mime_to_ext(mime_type)
    file_name = f"plan_{plan.id}_{int(datetime.utcnow().timestamp())}.{ext}"
    storage_path = str(Path(user_id) / "plans" / str(plan.id) / file_name).replace("\\", "/")

    upload = requests.post(
        f"{settings.supabase_url}/storage/v1/object/{settings.supabase_storage_bucket}/{storage_path}",
        headers={**_supabase_headers(mime_type), "x-upsert": "true"},
        data=image_bytes,
        timeout=60,
    )
    if upload.status_code not in (200, 201):
        raise RuntimeError(f"Plan image upload failed: {upload.status_code} {upload.text[:200]}")

    plan.image_url = _generate_signed_url(storage_path)
    plan.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(plan)
    return plan
