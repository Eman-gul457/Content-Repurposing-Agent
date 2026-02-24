from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.db_models import ContentPlan, ResearchItem
from backend.pollinations_service import build_pollinations_image_url

DEFAULT_POSTS_PER_WEEK = 3
WEEKDAY_PATTERN = [0, 2, 4, 6, 1]  # Mon, Wed, Fri, Sun, Tue
PLATFORM_TIMES = {
    "linkedin": (10, 30),
    "twitter": (13, 0),
    "facebook": (20, 0),
    "instagram": (18, 0),
    "blog_summary": (11, 0),
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


def create_content_plans(
    db: Session,
    user_id: str,
    run_id: int,
    platforms: list[str],
    language_pref: str,
    timezone_name: str,
    research_items: list[ResearchItem],
    posts_per_week: int = DEFAULT_POSTS_PER_WEEK,
) -> list[ContentPlan]:
    tz = ZoneInfo(timezone_name)
    now_local = datetime.now(tz)
    posts_per_week = max(2, min(5, posts_per_week))

    topics = [item.title for item in research_items if item.title] or ["Industry update", "Customer tip", "Behind the scenes"]
    plans: list[ContentPlan] = []

    for platform in platforms:
        hour, minute = PLATFORM_TIMES.get(platform, (12, 0))
        for idx in range(posts_per_week):
            weekday = WEEKDAY_PATTERN[idx % len(WEEKDAY_PATTERN)]
            local_slot = _next_local_slot(now_local + timedelta(days=idx), weekday, hour, minute)
            utc_slot = _local_to_utc_naive(local_slot)
            theme = topics[idx % len(topics)]
            image_prompt = (
                f"Professional social media visual for {platform}. Theme: {theme}. "
                f"Style: clean modern, marketing quality, high contrast."
            )
            row = ContentPlan(
                user_id=user_id,
                run_id=run_id,
                platform=platform,
                language_pref=language_pref,
                planned_for=utc_slot,
                status="planned",
                theme=theme,
                post_angle=f"{platform} angle #{idx + 1}: insight + practical takeaway",
                image_prompt=image_prompt,
                image_url=build_pollinations_image_url(image_prompt),
            )
            db.add(row)
            plans.append(row)

    db.commit()
    for row in plans:
        db.refresh(row)
    return plans
