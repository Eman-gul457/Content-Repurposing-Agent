from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.ai_service import generate_platform_posts
from backend.auth import get_current_user_id
from backend.database import SessionLocal, get_db, init_db
from backend.db_models import GeneratedPost, PostStatus, SocialAccount
from backend.linkedin_service import create_linkedin_authorization_url, handle_linkedin_callback, publish_to_linkedin
from backend.scheduler import create_scheduler
from backend.schemas import (
    GenerateRequest,
    GenerateResponse,
    DraftPost,
    UpdatePostRequest,
    UpdateStatusRequest,
    ScheduleRequest,
    PublishNowRequest,
    SocialAccountResponse,
    LinkedInConnectStartResponse,
    HistoryResponse,
)
from config.settings import settings

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin] if settings.cors_origin != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = None


def _serialize_post(post: GeneratedPost) -> DraftPost:
    return DraftPost(
        id=post.id,
        platform=post.platform,
        input_content=post.input_content,
        generated_text=post.generated_text,
        edited_text=post.edited_text,
        status=post.status,
        scheduled_at=post.scheduled_at,
        posted_at=post.posted_at,
        last_error=post.last_error,
        created_at=post.created_at,
    )


@app.on_event("startup")
def startup() -> None:
    global scheduler
    init_db()
    scheduler = create_scheduler(SessionLocal)
    scheduler.start()


@app.on_event("shutdown")
def shutdown() -> None:
    if scheduler:
        scheduler.shutdown(wait=False)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/generate", response_model=GenerateResponse)
def generate_content(
    payload: GenerateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> GenerateResponse:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    outputs = generate_platform_posts(content)
    created: list[GeneratedPost] = []

    for platform, text in outputs.items():
        row = GeneratedPost(
            user_id=user_id,
            platform=platform,
            input_content=content,
            generated_text=text,
            edited_text="",
            status=PostStatus.draft.value,
        )
        db.add(row)
        created.append(row)

    db.commit()
    for row in created:
        db.refresh(row)

    return GenerateResponse(drafts=[_serialize_post(row) for row in created])


@app.get("/api/drafts", response_model=HistoryResponse)
def get_drafts(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> HistoryResponse:
    rows = (
        db.query(GeneratedPost)
        .filter(GeneratedPost.user_id == user_id)
        .order_by(GeneratedPost.created_at.desc())
        .all()
    )
    return HistoryResponse(posts=[_serialize_post(r) for r in rows])


@app.patch("/api/posts/{post_id}", response_model=DraftPost)
def update_post(
    post_id: int,
    payload: UpdatePostRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> DraftPost:
    post = db.query(GeneratedPost).filter(GeneratedPost.id == post_id, GeneratedPost.user_id == user_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    post.edited_text = payload.edited_text.strip()
    post.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(post)
    return _serialize_post(post)


@app.patch("/api/posts/{post_id}/status", response_model=DraftPost)
def update_status(
    post_id: int,
    payload: UpdateStatusRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> DraftPost:
    post = db.query(GeneratedPost).filter(GeneratedPost.id == post_id, GeneratedPost.user_id == user_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    post.status = payload.status
    post.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(post)
    return _serialize_post(post)


@app.patch("/api/posts/{post_id}/schedule", response_model=DraftPost)
def schedule_post(
    post_id: int,
    payload: ScheduleRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> DraftPost:
    post = db.query(GeneratedPost).filter(GeneratedPost.id == post_id, GeneratedPost.user_id == user_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    post.status = PostStatus.scheduled.value
    post.scheduled_at = payload.scheduled_at.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    post.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(post)
    return _serialize_post(post)


@app.post("/api/posts/{post_id}/publish", response_model=DraftPost)
def publish_post_now(
    post_id: int,
    payload: PublishNowRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> DraftPost:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Explicit permission required")

    post = db.query(GeneratedPost).filter(GeneratedPost.id == post_id, GeneratedPost.user_id == user_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.platform != "linkedin":
        raise HTTPException(status_code=400, detail="Only LinkedIn publishing is enabled right now")

    if post.status not in [PostStatus.approved.value, PostStatus.scheduled.value, PostStatus.failed.value]:
        raise HTTPException(status_code=400, detail="Post must be approved or scheduled before publishing")

    content = post.edited_text.strip() if post.edited_text.strip() else post.generated_text

    try:
        result = publish_to_linkedin(db, user_id, content)
        post.status = PostStatus.posted.value
        post.posted_at = datetime.utcnow()
        post.external_post_id = result.get("external_post_id", "")
        post.last_error = ""
    except Exception as exc:
        post.status = PostStatus.failed.value
        post.last_error = str(exc)
        db.commit()
        db.refresh(post)
        raise HTTPException(status_code=500, detail=f"Publish failed: {exc}") from exc

    db.commit()
    db.refresh(post)
    return _serialize_post(post)


@app.get("/api/social-accounts", response_model=list[SocialAccountResponse])
def social_accounts(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[SocialAccountResponse]:
    linkedin = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "linkedin")
        .first()
    )

    return [
        SocialAccountResponse(
            platform="linkedin",
            connected=linkedin is not None,
            account_name=linkedin.account_name if linkedin else None,
        ),
        SocialAccountResponse(platform="twitter", connected=False, account_name=None),
        SocialAccountResponse(platform="facebook", connected=False, account_name=None),
    ]


@app.get("/api/linkedin/connect/start", response_model=LinkedInConnectStartResponse)
def linkedin_connect_start(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> LinkedInConnectStartResponse:
    url = create_linkedin_authorization_url(db, user_id)
    return LinkedInConnectStartResponse(authorization_url=url)


@app.get("/api/linkedin/connect/callback")
def linkedin_connect_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    redirect_base = settings.frontend_url.rstrip("/") if settings.frontend_url else ""
    success_url = f"{redirect_base}/index.html?linkedin=connected" if redirect_base else "/index.html?linkedin=connected"
    try:
        handle_linkedin_callback(db, code, state)
    except Exception as exc:
        error_url = f"{redirect_base}/index.html?linkedin=error&message={str(exc)}" if redirect_base else f"/index.html?linkedin=error&message={str(exc)}"
        return RedirectResponse(url=error_url)

    return RedirectResponse(url=success_url)
