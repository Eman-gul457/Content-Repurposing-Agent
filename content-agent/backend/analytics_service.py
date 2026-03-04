from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.db_models import ClientPerformanceMetric, PostClientLink


def _metric_seed_value(post_id: int, platform: str, salt: str) -> int:
    digest = hashlib.sha256(f"{post_id}:{platform}:{salt}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _synthetic_values(post_id: int, platform: str) -> dict[str, int]:
    likes = 30 + (_metric_seed_value(post_id, platform, "likes") % 170)
    shares = 5 + (_metric_seed_value(post_id, platform, "shares") % 35)
    comments = 4 + (_metric_seed_value(post_id, platform, "comments") % 28)
    clicks = 20 + (_metric_seed_value(post_id, platform, "clicks") % 160)
    follower_growth = 1 + (_metric_seed_value(post_id, platform, "followers") % 18)
    return {
        "likes": likes,
        "shares": shares,
        "comments": comments,
        "clicks": clicks,
        "follower_growth": follower_growth,
    }


def resolve_post_client_id(db: Session, user_id: str, post_id: int) -> int | None:
    row = (
        db.query(PostClientLink)
        .filter(PostClientLink.user_id == user_id, PostClientLink.post_id == post_id)
        .first()
    )
    return row.client_id if row else None


def record_publish_metric(
    db: Session,
    *,
    user_id: str,
    post_id: int,
    platform: str,
    posted_at: datetime | None = None,
    client_id: int | None = None,
) -> None:
    target_client_id = client_id or resolve_post_client_id(db, user_id, post_id)
    if not target_client_id:
        return
    metric_dt = (posted_at or datetime.utcnow()).replace(hour=0, minute=0, second=0, microsecond=0)
    values = _synthetic_values(post_id, platform)

    row = (
        db.query(ClientPerformanceMetric)
        .filter(
            ClientPerformanceMetric.user_id == user_id,
            ClientPerformanceMetric.client_id == target_client_id,
            ClientPerformanceMetric.platform == platform,
            ClientPerformanceMetric.metric_date == metric_dt,
        )
        .first()
    )
    if not row:
        row = ClientPerformanceMetric(
            user_id=user_id,
            client_id=target_client_id,
            platform=platform,
            metric_date=metric_dt,
            likes=values["likes"],
            shares=values["shares"],
            comments=values["comments"],
            clicks=values["clicks"],
            follower_growth=values["follower_growth"],
        )
        db.add(row)
    else:
        row.likes += values["likes"]
        row.shares += values["shares"]
        row.comments += values["comments"]
        row.clicks += values["clicks"]
        row.follower_growth += values["follower_growth"]


def aggregate_metrics(
    db: Session,
    *,
    user_id: str,
    days: int = 14,
    client_id: int | None = None,
) -> tuple[dict[str, int], list[dict[str, int | str]]]:
    days = max(1, min(days, 90))
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=days - 1)

    q = db.query(ClientPerformanceMetric).filter(
        ClientPerformanceMetric.user_id == user_id,
        ClientPerformanceMetric.metric_date >= start,
    )
    if client_id:
        q = q.filter(ClientPerformanceMetric.client_id == client_id)
    rows = q.all()

    by_day: dict[str, dict[str, int]] = {}
    totals = {"likes": 0, "shares": 0, "comments": 0, "clicks": 0, "follower_growth": 0}

    for row in rows:
        key = row.metric_date.strftime("%Y-%m-%d")
        bucket = by_day.setdefault(key, {"likes": 0, "shares": 0, "comments": 0, "clicks": 0, "follower_growth": 0})
        bucket["likes"] += int(row.likes or 0)
        bucket["shares"] += int(row.shares or 0)
        bucket["comments"] += int(row.comments or 0)
        bucket["clicks"] += int(row.clicks or 0)
        bucket["follower_growth"] += int(row.follower_growth or 0)

        totals["likes"] += int(row.likes or 0)
        totals["shares"] += int(row.shares or 0)
        totals["comments"] += int(row.comments or 0)
        totals["clicks"] += int(row.clicks or 0)
        totals["follower_growth"] += int(row.follower_growth or 0)

    series: list[dict[str, int | str]] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        key = day.strftime("%Y-%m-%d")
        vals = by_day.get(key, {"likes": 0, "shares": 0, "comments": 0, "clicks": 0, "follower_growth": 0})
        series.append(
            {
                "date": key,
                "likes": vals["likes"],
                "shares": vals["shares"],
                "comments": vals["comments"],
                "clicks": vals["clicks"],
                "follower_growth": vals["follower_growth"],
            }
        )

    return totals, series
