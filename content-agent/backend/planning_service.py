from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.db_models import ContentPlan, ResearchItem

DEFAULT_POSTS_PER_WEEK = 3
WEEKDAY_PATTERN = [0, 2, 4, 6, 1]  # Mon, Wed, Fri, Sun, Tue
PLATFORM_TIMES = {
    "linkedin": (10, 30),
    "twitter": (13, 0),
    "facebook": (20, 0),
    "instagram": (18, 0),
    "blog_summary": (11, 0),
}
ANGLE_TEMPLATES = [
    "educational insight with one actionable tip",
    "myth vs reality angle with concise explanation",
    "customer pain point and practical solution",
    "quick checklist format with clear CTA",
    "story-driven lesson with measurable outcome",
]
PLATFORM_STYLE_HINT = {
    "linkedin": "thought leadership visual, professional and clean",
    "twitter": "bold social card, high contrast and concise text",
    "facebook": "friendly community-style graphic, warm and clear",
    "instagram": "modern portrait social design, premium and vibrant",
    "blog_summary": "editorial summary card, minimal and readable",
}


def _next_local_slot(now_local: datetime, weekday: int, hour: int, minute: int) -> datetime:
    days_ahead = (weekday - now_local.weekday()) % 7
    candidate = now_local + timedelta(days=days_ahead)
    candidate = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=7)
    return candidate


def _local_to_utc_naive(dt_local: datetime) -> datetime:
    return dt_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _clean_theme(raw: str, fallback: str) -> str:
    text = (raw or "").strip()
    if not text:
        return fallback
    text = re.sub(r"^prior\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\spost\s*#?\d+\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -:")
    return text or fallback


def create_content_plans(
    db: Session,
    user_id: str,
    run_id: int,
    platforms: list[str],
    language_pref: str,
    timezone_name: str,
    research_items: list[ResearchItem],
    business_name: str = "",
    niche: str = "",
    audience: str = "",
    tone: str = "",
    region: str = "",
    posts_per_week: int = DEFAULT_POSTS_PER_WEEK,
) -> list[ContentPlan]:
    tz = ZoneInfo(timezone_name)
    now_local = datetime.now(tz)
    posts_per_week = max(2, min(5, posts_per_week))

    preferred_research = [item.title for item in research_items if item.title and item.source != "existing_posts"]
    fallback_research = [item.title for item in research_items if item.title]
    topics_raw = preferred_research or fallback_research or []
    topics = [_clean_theme(x, "Industry insight") for x in topics_raw]
    if not topics:
        base_niche = (niche or "industry").strip()
        topics = [
            f"{base_niche.title()} trend to watch",
            "Common mistake and fix",
            "Practical weekly tip",
            "Customer success idea",
            "Quick framework for better results",
        ]

    brand = (business_name or "Your brand").strip()
    audience_text = (audience or "target audience").strip()
    tone_text = (tone or "professional").strip()
    region_text = (region or "global").strip()
    plans: list[ContentPlan] = []

    for platform in platforms:
        hour, minute = PLATFORM_TIMES.get(platform, (12, 0))
        for idx in range(posts_per_week):
            weekday = WEEKDAY_PATTERN[idx % len(WEEKDAY_PATTERN)]
            local_slot = _next_local_slot(now_local + timedelta(days=idx), weekday, hour, minute)
            utc_slot = _local_to_utc_naive(local_slot)
            theme = topics[(idx + len(platform)) % len(topics)]
            angle = ANGLE_TEMPLATES[idx % len(ANGLE_TEMPLATES)]
            style_hint = PLATFORM_STYLE_HINT.get(platform, "professional social media visual")
            image_prompt = (
                f"Design a polished {platform} post image for {brand}. "
                f"Theme: {theme}. Angle: {angle}. Audience: {audience_text}. "
                f"Tone: {tone_text}. Region context: {region_text}. "
                f"Style: {style_hint}. Avoid logos from other brands."
            )
            row = ContentPlan(
                user_id=user_id,
                run_id=run_id,
                platform=platform,
                language_pref=language_pref,
                planned_for=utc_slot,
                status="planned",
                theme=theme,
                post_angle=f"{platform} angle #{idx + 1}: {angle}",
                image_prompt=image_prompt,
                image_url="",
            )
            db.add(row)
            plans.append(row)

    db.commit()
    for row in plans:
        db.refresh(row)
    return plans
