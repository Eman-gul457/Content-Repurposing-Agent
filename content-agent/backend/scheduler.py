from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from backend.db_models import GeneratedPost, PostStatus
from backend.media_service import list_post_media, refresh_media_signed_urls
from backend.linkedin_service import publish_to_linkedin


def process_scheduled_posts(db: Session) -> None:
    now = datetime.utcnow()
    posts = (
        db.query(GeneratedPost)
        .filter(GeneratedPost.status == PostStatus.scheduled.value, GeneratedPost.scheduled_at <= now)
        .all()
    )

    for post in posts:
        try:
            content = post.edited_text.strip() if post.edited_text.strip() else post.generated_text
            media = list_post_media(db, post.user_id, post.id)
            refresh_media_signed_urls(db, media)
            result = publish_to_linkedin(db, post.user_id, content, media_items=media)
            post.status = PostStatus.posted.value
            post.posted_at = now
            post.external_post_id = result.get("external_post_id", "")
            post.last_error = ""
            db.commit()
        except Exception as exc:
            post.status = PostStatus.failed.value
            post.last_error = str(exc)
            db.commit()


def create_scheduler(session_factory):
    scheduler = BackgroundScheduler()

    def _job_wrapper():
        db = session_factory()
        try:
            process_scheduled_posts(db)
        finally:
            db.close()

    scheduler.add_job(_job_wrapper, "interval", minutes=1, id="scheduled-publisher", replace_existing=True)
    return scheduler
