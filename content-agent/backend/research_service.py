from __future__ import annotations

import html
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree

import requests
from sqlalchemy.orm import Session

from backend.db_models import GeneratedPost, ResearchItem

MAX_RESEARCH_ITEMS_PER_DAY = 5
RSS_TIMEOUT = 30


def _clean_text(value: str) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _parse_rss(xml_text: str) -> list[dict]:
    out: list[dict] = []
    root = ElementTree.fromstring(xml_text)
    for item in root.findall(".//item"):
        title = _clean_text(item.findtext("title") or "")
        link = _clean_text(item.findtext("link") or "")
        desc = _clean_text(item.findtext("description") or item.findtext("content:encoded") or "")
        pub = item.findtext("pubDate") or ""
        published_at = None
        if pub:
            try:
                published_at = parsedate_to_datetime(pub).replace(tzinfo=None)
            except Exception:
                published_at = None
        if title and link:
            out.append(
                {
                    "title": title,
                    "url": link,
                    "snippet": desc[:400],
                    "published_at": published_at,
                }
            )
    return out


def _fetch_rss(source: str, url: str, limit: int) -> list[dict]:
    headers = {"User-Agent": "ContentRepurposingAgent/1.0"}
    try:
        response = requests.get(url, headers=headers, timeout=RSS_TIMEOUT)
        if response.status_code >= 400:
            return []
        items = _parse_rss(response.text)
    except Exception:
        return []

    out = []
    for item in items[: limit * 2]:
        item["source"] = source
        out.append(item)
    return out[:limit]


def _collect_existing_post_insights(db: Session, user_id: str, niche: str, limit: int) -> list[dict]:
    rows = (
        db.query(GeneratedPost)
        .filter(GeneratedPost.user_id == user_id)
        .order_by(GeneratedPost.created_at.desc())
        .limit(limit * 3)
        .all()
    )
    out: list[dict] = []
    niche_l = niche.lower().strip()
    for row in rows:
        text = (row.edited_text.strip() if row.edited_text.strip() else row.generated_text).strip()
        if not text:
            continue
        if niche_l and niche_l not in text.lower():
            continue
        out.append(
            {
                "source": "existing_posts",
                "title": f"Prior {row.platform} post #{row.id}",
                "url": "",
                "snippet": text[:400],
                "published_at": row.created_at,
            }
        )
        if len(out) >= limit:
            break
    return out


def collect_research_items(
    db: Session,
    user_id: str,
    run_id: int,
    business_name: str,
    niche: str,
    region: str,
    audience: str,
    max_items_per_day: int = MAX_RESEARCH_ITEMS_PER_DAY,
) -> list[ResearchItem]:
    now = datetime.utcnow()
    start_of_day = datetime(now.year, now.month, now.day)
    end_of_day = start_of_day + timedelta(days=1)

    already_count = (
        db.query(ResearchItem)
        .filter(
            ResearchItem.user_id == user_id,
            ResearchItem.created_at >= start_of_day,
            ResearchItem.created_at < end_of_day,
        )
        .count()
    )
    remaining = max_items_per_day - already_count
    if remaining <= 0:
        return []

    query = " ".join(x for x in [business_name, niche, audience, region] if x).strip()
    if not query:
        query = niche or business_name or "business"

    google_url = f"https://news.google.com/rss/search?q={quote_plus(query)}"
    reddit_url = f"https://www.reddit.com/search.rss?q={quote_plus(query)}&sort=new&t=week"
    hn_url = f"https://hnrss.org/newest?q={quote_plus(query)}"

    candidates: list[dict] = []
    candidates.extend(_fetch_rss("google_news", google_url, remaining))
    candidates.extend(_fetch_rss("reddit", reddit_url, remaining))
    candidates.extend(_fetch_rss("rss", hn_url, remaining))
    candidates.extend(_collect_existing_post_insights(db, user_id, niche, remaining))

    seen: set[str] = set()
    created: list[ResearchItem] = []
    for item in candidates:
        key = (item.get("url") or item.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        row = ResearchItem(
            user_id=user_id,
            run_id=run_id,
            source=item.get("source", "rss"),
            title=item.get("title", "")[:800],
            url=item.get("url", "")[:1500],
            snippet=item.get("snippet", "")[:1500],
            published_at=item.get("published_at"),
        )
        db.add(row)
        created.append(row)
        if len(created) >= remaining:
            break

    db.commit()
    for row in created:
        db.refresh(row)
    return created
