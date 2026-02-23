from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.ai_service import generate_platform_posts
from backend.auth import get_current_user_id
from backend.database import SessionLocal, get_db, init_db
from backend.db_models import GeneratedPost, MediaAsset, PostStatus, SocialAccount
from backend.linkedin_service import create_linkedin_authorization_url, handle_linkedin_callback, publish_to_linkedin
from backend.media_service import list_post_media, refresh_media_signed_urls, upload_media_base64
from backend.scheduler import create_scheduler
from backend.twitter_service import create_twitter_authorization_url, handle_twitter_callback, publish_to_twitter
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
    MediaAssetResponse,
    UploadMediaRequest,
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


def _serialize_media(item: MediaAsset) -> MediaAssetResponse:
    return MediaAssetResponse(
        id=item.id,
        post_id=item.post_id,
        platform=item.platform,
        file_name=item.file_name,
        mime_type=item.mime_type,
        file_size=item.file_size,
        file_url=item.file_url,
        platform_asset_id=item.platform_asset_id,
        upload_status=item.upload_status,
        last_error=item.last_error,
        created_at=item.created_at,
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

    if post.platform not in ["linkedin", "twitter"]:
        raise HTTPException(status_code=400, detail="Publishing is currently enabled for LinkedIn and Twitter only")

    if post.status not in [PostStatus.approved.value, PostStatus.scheduled.value, PostStatus.failed.value]:
        raise HTTPException(status_code=400, detail="Post must be approved or scheduled before publishing")

    content = post.edited_text.strip() if post.edited_text.strip() else post.generated_text
    try:
        if post.platform == "linkedin":
            media = list_post_media(db, user_id, post.id)
            refresh_media_signed_urls(db, media)
            result = publish_to_linkedin(db, user_id, content, media_items=media)
        else:
            media = list_post_media(db, user_id, post.id)
            result = publish_to_twitter(db, user_id, content, media_items=media)
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


@app.post("/api/uploads", response_model=MediaAssetResponse)
def upload_media(
    payload: UploadMediaRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> MediaAssetResponse:
    try:
        row = upload_media_base64(
            db=db,
            user_id=user_id,
            post_id=payload.post_id,
            file_name=payload.file_name,
            mime_type=payload.mime_type,
            content_base64=payload.content_base64,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_media(row)


@app.get("/api/posts/{post_id}/media", response_model=list[MediaAssetResponse])
def list_media(
    post_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[MediaAssetResponse]:
    items = list_post_media(db, user_id, post_id)
    refresh_media_signed_urls(db, items)
    return [_serialize_media(x) for x in items]


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
    twitter = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "twitter")
        .first()
    )

    return [
        SocialAccountResponse(
            platform="linkedin",
            connected=linkedin is not None,
            account_name=linkedin.account_name if linkedin else None,
        ),
        SocialAccountResponse(
            platform="twitter",
            connected=twitter is not None,
            account_name=twitter.account_name if twitter else None,
        ),
        SocialAccountResponse(platform="facebook", connected=False, account_name=None),
    ]


@app.get("/api/linkedin/connect/start", response_model=LinkedInConnectStartResponse)
def linkedin_connect_start(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> LinkedInConnectStartResponse:
    url = create_linkedin_authorization_url(db, user_id)
    return LinkedInConnectStartResponse(authorization_url=url)


@app.get("/api/twitter/connect/start", response_model=LinkedInConnectStartResponse)
def twitter_connect_start(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> LinkedInConnectStartResponse:
    url = create_twitter_authorization_url(db, user_id)
    return LinkedInConnectStartResponse(authorization_url=url)


@app.get("/api/linkedin/connect/callback")
def linkedin_connect_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    redirect_base = settings.frontend_url.rstrip("/") if settings.frontend_url else ""
    success_url = f"{redirect_base}/index.html?linkedin=connected" if redirect_base else "/index.html?linkedin=connected"
    if error:
        description = (error_description or "").replace("+", " ")
        message = f"LinkedIn OAuth error: {error}. {description}".strip()
        error_url = f"{redirect_base}/index.html?linkedin=error&message={message}" if redirect_base else f"/index.html?linkedin=error&message={message}"
        return RedirectResponse(url=error_url)

    if not code or not state:
        message = "LinkedIn callback missing code/state. Check app redirect URI and scopes."
        error_url = f"{redirect_base}/index.html?linkedin=error&message={message}" if redirect_base else f"/index.html?linkedin=error&message={message}"
        return RedirectResponse(url=error_url)

    try:
        handle_linkedin_callback(db, code, state)
    except Exception as exc:
        error_url = f"{redirect_base}/index.html?linkedin=error&message={str(exc)}" if redirect_base else f"/index.html?linkedin=error&message={str(exc)}"
        return RedirectResponse(url=error_url)

    return RedirectResponse(url=success_url)


@app.get("/api/twitter/connect/callback")
def twitter_connect_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    redirect_base = settings.frontend_url.rstrip("/") if settings.frontend_url else ""
    success_url = f"{redirect_base}/index.html?twitter=connected" if redirect_base else "/index.html?twitter=connected"
    if error:
        description = (error_description or "").replace("+", " ")
        message = f"Twitter OAuth error: {error}. {description}".strip()
        error_url = f"{redirect_base}/index.html?twitter=error&message={message}" if redirect_base else f"/index.html?twitter=error&message={message}"
        return RedirectResponse(url=error_url)

    if not code or not state:
        message = "Twitter callback missing code/state. Check app redirect URI and scopes."
        error_url = f"{redirect_base}/index.html?twitter=error&message={message}" if redirect_base else f"/index.html?twitter=error&message={message}"
        return RedirectResponse(url=error_url)

    try:
        handle_twitter_callback(db, code, state)
    except Exception as exc:
        error_url = f"{redirect_base}/index.html?twitter=error&message={str(exc)}" if redirect_base else f"/index.html?twitter=error&message={str(exc)}"
        return RedirectResponse(url=error_url)

    return RedirectResponse(url=success_url)
