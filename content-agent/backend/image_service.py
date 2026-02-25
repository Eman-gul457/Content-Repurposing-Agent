from __future__ import annotations

import html
import hashlib
import random
import re
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
NEGATIVE_HINTS = {"constraint", "problem", "weak", "linear", "hunting", "slow", "bottleneck"}
POSITIVE_HINTS = {
    "approved",
    "outcome",
    "automation",
    "pipeline",
    "system",
    "engine",
    "scale",
    "throughput",
    "efficiency",
}


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
    h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)
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


def _sanitize_visual_line(line: str) -> str:
    text = (line or "").strip()
    if not text:
        return ""
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"hashtag#\w+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -:,.")
    return text.strip()


def _extract_visual_points(text: str, max_points: int = 8) -> list[str]:
    if not text.strip():
        return []
    raw_lines = [x.strip() for x in text.splitlines() if x.strip()]
    candidates: list[str] = []
    for ln in raw_lines:
        cleaned = _sanitize_visual_line(ln)
        if len(cleaned) >= 12:
            candidates.append(cleaned)

    if len(candidates) < max_points:
        split_lines: list[str] = []
        for block in raw_lines:
            split_lines.extend(re.split(r"[.!?;]\s+", block))
        for part in split_lines:
            cleaned = _sanitize_visual_line(part)
            if len(cleaned) >= 16:
                candidates.append(cleaned)

    unique: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item[:120])
        if len(unique) >= max_points:
            break
    return unique


def _split_points_for_columns(points: list[str]) -> tuple[list[str], list[str]]:
    if not points:
        return [], []

    left: list[str] = []
    right: list[str] = []
    for point in points:
        low = point.casefold()
        neg = any(k in low for k in NEGATIVE_HINTS)
        pos = any(k in low for k in POSITIVE_HINTS)
        if neg and not pos:
            left.append(point)
        elif pos and not neg:
            right.append(point)
        elif len(left) <= len(right):
            left.append(point)
        else:
            right.append(point)

    if not left or not right:
        half = max(1, len(points) // 2)
        left = points[:half]
        right = points[half:]
    return left[:5], right[:5]


def _pick_headline(theme: str, points: list[str], platform: str) -> str:
    theme_clean = _sanitize_visual_line(theme)
    if theme_clean and len(theme_clean) >= 8:
        return theme_clean[:92]
    for p in points:
        if 18 <= len(p) <= 92:
            return p
    return f"{platform.upper()} strategy breakdown"


def _pick_core_message(angle: str, points: list[str]) -> str:
    angle_clean = _sanitize_visual_line(angle)
    if angle_clean and len(angle_clean) >= 10:
        return angle_clean[:90]
    for p in points:
        low = p.casefold()
        if "throughput" in low or "scale" in low or "outcome" in low:
            return p[:90]
    return "Software is not the product. Throughput is."


def _svg_bullet_list(
    points: list[str],
    *,
    x: int,
    y: int,
    width: int,
    max_lines: int,
    line_height: int,
    font_size: int,
    color: str,
) -> str:
    rows: list[str] = []
    cursor = y
    for point in points[:max_lines]:
        wrapped = _wrap_text(point, max_len=34, max_lines=2)
        if not wrapped:
            continue
        rows.append(
            f'<rect x="{x}" y="{cursor - int(line_height * 0.8)}" width="{width}" '
            f'height="{int(line_height * (1.35 if len(wrapped) == 1 else 2.1))}" rx="10" '
            f'fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.07)"/>'
        )
        rows.append(
            f'<circle cx="{x + 14}" cy="{cursor - 4}" r="4" fill="{color}" />'
        )
        text_lines = _svg_text_block(
            wrapped,
            x + 28,
            cursor,
            int(line_height * 0.9),
            font_size,
            "#e6edf8",
            550,
        )
        rows.append(text_lines)
        cursor += int(line_height * (1.75 if len(wrapped) == 1 else 2.45))
    return "\n  ".join(rows)


def _build_infographic_svg(
    platform: str,
    theme: str,
    angle: str,
    source_text: str,
    business_name: str,
    width: int,
    height: int,
    style: dict[str, str],
    layout: str,
) -> bytes:
    points = _extract_visual_points(source_text, max_points=10)
    headline = _pick_headline(theme, points, platform)
    core_message = _pick_core_message(angle, points)
    brand = html.escape((business_name or "Your Brand")[:50])

    left_points, right_points = _split_points_for_columns(points or [theme, angle])
    left_title = "Current Pattern"
    right_title = "Execution Model"

    title_lines = _wrap_text(headline, max_len=36 if width >= height else 28, max_lines=2)
    core_lines = _wrap_text(core_message, max_len=40 if width >= height else 30, max_lines=2)
    title_size = max(42, int(height * (0.056 if width >= height else 0.05)))
    core_size = max(23, int(height * 0.03))

    if width >= height:
        col_top = int(height * 0.28)
        col_h = int(height * 0.58)
        col_w = int(width * 0.39)
        left_x = int(width * 0.06)
        right_x = int(width * 0.55)
        divider_y = int(height * 0.49)
        list_left = _svg_bullet_list(
            left_points,
            x=left_x + 14,
            y=col_top + 72,
            width=col_w - 28,
            max_lines=4,
            line_height=34,
            font_size=20,
            color="#f59e0b",
        )
        list_right = _svg_bullet_list(
            right_points,
            x=right_x + 14,
            y=col_top + 72,
            width=col_w - 28,
            max_lines=4,
            line_height=34,
            font_size=20,
            color="#22d3ee",
        )
        panel = f"""
  <rect x="{left_x}" y="{col_top}" width="{col_w}" height="{col_h}" rx="16" fill="rgba(5,9,22,0.55)" stroke="rgba(245,158,11,0.35)"/>
  <rect x="{right_x}" y="{col_top}" width="{col_w}" height="{col_h}" rx="16" fill="rgba(5,9,22,0.55)" stroke="rgba(34,211,238,0.35)"/>
  <text x="{left_x + 16}" y="{col_top + 38}" font-family="Inter, Arial, sans-serif" font-weight="700" font-size="22" fill="#fbbf24">{left_title}</text>
  <text x="{right_x + 16}" y="{col_top + 38}" font-family="Inter, Arial, sans-serif" font-weight="700" font-size="22" fill="#67e8f9">{right_title}</text>
  {list_left}
  {list_right}
  <line x1="{int(width * 0.47)}" y1="{divider_y}" x2="{int(width * 0.53)}" y2="{divider_y}" stroke="#fcd34d" stroke-width="3"/>
  <polygon points="{int(width * 0.53)},{divider_y} {int(width * 0.522)},{divider_y - 8} {int(width * 0.522)},{divider_y + 8}" fill="#fcd34d"/>
"""
    else:
        col_top = int(height * 0.33)
        row_h = int(height * 0.25)
        left_x = int(width * 0.06)
        col_w = int(width * 0.88)
        right_y = col_top + row_h + 18
        list_left = _svg_bullet_list(
            left_points,
            x=left_x + 14,
            y=col_top + 64,
            width=col_w - 28,
            max_lines=3,
            line_height=30,
            font_size=17,
            color="#f59e0b",
        )
        list_right = _svg_bullet_list(
            right_points,
            x=left_x + 14,
            y=right_y + 64,
            width=col_w - 28,
            max_lines=3,
            line_height=30,
            font_size=17,
            color="#22d3ee",
        )
        panel = f"""
  <rect x="{left_x}" y="{col_top}" width="{col_w}" height="{row_h}" rx="14" fill="rgba(5,9,22,0.55)" stroke="rgba(245,158,11,0.35)"/>
  <rect x="{left_x}" y="{right_y}" width="{col_w}" height="{row_h}" rx="14" fill="rgba(5,9,22,0.55)" stroke="rgba(34,211,238,0.35)"/>
  <text x="{left_x + 14}" y="{col_top + 34}" font-family="Inter, Arial, sans-serif" font-weight="700" font-size="18" fill="#fbbf24">{left_title}</text>
  <text x="{left_x + 14}" y="{right_y + 34}" font-family="Inter, Arial, sans-serif" font-weight="700" font-size="18" fill="#67e8f9">{right_title}</text>
  {list_left}
  {list_right}
"""

    footer_y = int(height * 0.93)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{style["bg_1"]}"/>
      <stop offset="100%" stop-color="{style["bg_2"]}"/>
    </linearGradient>
    <linearGradient id="topline" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#f59e0b"/>
      <stop offset="100%" stop-color="#22d3ee"/>
    </linearGradient>
  </defs>
  <rect width="{width}" height="{height}" fill="url(#bg)"/>
  <rect x="{int(width * 0.04)}" y="{int(height * 0.04)}" width="{int(width * 0.92)}" height="{int(height * 0.92)}" rx="{int(height * 0.03)}" fill="rgba(2,6,23,0.35)" stroke="rgba(255,255,255,0.08)"/>
  <rect x="{int(width * 0.08)}" y="{int(height * 0.13)}" width="{int(width * 0.84)}" height="4" rx="2" fill="url(#topline)"/>
  {_svg_text_block(title_lines, int(width * 0.08), int(height * 0.1), int(title_size * 1.1), title_size, "#f8fafc", 820)}
  {_svg_text_block(core_lines, int(width * 0.08), int(height * 0.22), int(core_size * 1.3), core_size, "#cbd5e1", 600)}
  {panel}
  <text x="{int(width * 0.08)}" y="{footer_y}" font-family="Inter, Arial, sans-serif" font-weight="700" font-size="{max(20, int(height * 0.032))}" fill="#f8fafc">{brand}</text>
  <text x="{int(width * 0.08)}" y="{footer_y + max(20, int(height * 0.03))}" font-family="Inter, Arial, sans-serif" font-size="{max(14, int(height * 0.022))}" fill="#9db0cf">Execution architecture for validated demand</text>
</svg>"""
    return svg.encode("utf-8")


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


def generate_plan_image(
    db: Session,
    user_id: str,
    plan_id: int,
    business_name: str = "",
    source_text: str = "",
) -> ContentPlan:
    plan = db.query(ContentPlan).filter(ContentPlan.id == plan_id, ContentPlan.user_id == user_id).first()
    if not plan:
        raise RuntimeError("Plan not found")

    prompt = (plan.image_prompt or f"Social media creative for {plan.platform} {plan.theme}").strip()
    width, height = _pick_dimensions(plan.platform)
    seed = f"{plan.id}:{plan.platform}:{plan.theme}:{plan.post_angle}"
    style = _pick_style(seed)
    layout = _pick_layout(seed)
    visual_source = "\n".join(
        x.strip()
        for x in [source_text, plan.theme, plan.post_angle, prompt]
        if (x or "").strip()
    )
    try:
        image_bytes = _build_infographic_svg(
            plan.platform,
            plan.theme,
            plan.post_angle,
            visual_source,
            business_name,
            width,
            height,
            style,
            layout,
        )
        mime_type = "image/svg+xml"
    except Exception:
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
