from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from backend.db_models import GeneratedPost, PostStatus, PublishJob
from backend.media_service import list_post_media, refresh_media_signed_urls
from backend.linkedin_service import publish_to_linkedin


def _touch_job(db: Session, post: GeneratedPost, status: str, error: str = "") -> None:
    row = (
        db.query(PublishJob)
        .filter(PublishJob.user_id == post.user_id, PublishJob.post_id == post.id)
        .first()
    )
    if not row:
        row = PublishJob(user_id=post.user_id, post_id=post.id, platform=post.platform, status=status)
        db.add(row)
    else:
        row.status = status
    now = datetime.utcnow()
    row.attempted_at = now
    if status == "posted":
        row.completed_at = now
    row.error_message = error


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
            if post.platform == "linkedin":
                media = list_post_media(db, post.user_id, post.id)
                refresh_media_signed_urls(db, media)
                result = publish_to_linkedin(db, post.user_id, content, media_items=media)
            elif post.platform == "twitter":
                post.status = PostStatus.failed.value
                post.last_error = "Twitter free mode does not support automatic scheduling/publishing."
                _touch_job(db, post, "failed", post.last_error)
                db.commit()
                continue
            else:
                post.status = PostStatus.failed.value
                post.last_error = f"Unsupported platform for scheduling: {post.platform}"
                _touch_job(db, post, "failed", post.last_error)
                db.commit()
                continue
            post.status = PostStatus.posted.value
            post.posted_at = now
            post.external_post_id = result.get("external_post_id", "")
            post.last_error = ""
            _touch_job(db, post, "posted", "")
            db.commit()
        except Exception as exc:
            post.status = PostStatus.failed.value
            post.last_error = str(exc)
            _touch_job(db, post, "failed", str(exc))
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
