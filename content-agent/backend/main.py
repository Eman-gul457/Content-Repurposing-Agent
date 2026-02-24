from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.ai_service import generate_platform_posts
from backend.auth import get_current_user_id
from backend.database import SessionLocal, get_db, init_db
from backend.db_models import (
    AgentRun,
    ApprovalRequest,
    ContentPlan,
    GeneratedPost,
    MediaAsset,
    PostStatus,
    PublishJob,
    ResearchItem,
    SocialAccount,
)
from backend.linkedin_service import create_linkedin_authorization_url, handle_linkedin_callback, publish_to_linkedin
from backend.media_service import list_post_media, refresh_media_signed_urls, upload_media_base64
from backend.planning_service import create_content_plans
from backend.research_service import collect_research_items
from backend.scheduler import create_scheduler
from backend.twitter_service import create_twitter_authorization_url, handle_twitter_callback
from backend.schemas import (
    AgentRunResponse,
    ContentPlanResponse,
    GenerateRequest,
    GenerateResponse,
    DraftPost,
    HistoryResponse,
    LinkedInConnectStartResponse,
    MediaAssetResponse,
    PublishNowRequest,
    ResearchItemResponse,
    ScheduleRequest,
    UpdatePostRequest,
    UpdateStatusRequest,
    SocialAccountResponse,
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


def _serialize_research(item: ResearchItem) -> ResearchItemResponse:
    return ResearchItemResponse(
        id=item.id,
        source=item.source,
        title=item.title,
        url=item.url,
        snippet=item.snippet,
        published_at=item.published_at,
        created_at=item.created_at,
    )


def _serialize_plan(item: ContentPlan) -> ContentPlanResponse:
    return ContentPlanResponse(
        id=item.id,
        platform=item.platform,
        language_pref=item.language_pref,
        planned_for=item.planned_for,
        status=item.status,
        theme=item.theme,
        post_angle=item.post_angle,
        image_prompt=item.image_prompt,
        image_url=item.image_url,
        created_at=item.created_at,
    )


def _ensure_approval_request(db: Session, user_id: str, post_id: int) -> None:
    row = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.user_id == user_id, ApprovalRequest.post_id == post_id)
        .first()
    )
    if row:
        return
    db.add(
        ApprovalRequest(
            user_id=user_id,
            post_id=post_id,
            status="pending",
            requested_at=datetime.utcnow(),
        )
    )


def _touch_publish_job(
    db: Session,
    post: GeneratedPost,
    *,
    status: str,
    error_message: str = "",
    scheduled_at: datetime | None = None,
    attempted: bool = False,
    completed: bool = False,
) -> None:
    row = (
        db.query(PublishJob)
        .filter(PublishJob.user_id == post.user_id, PublishJob.post_id == post.id)
        .first()
    )
    if not row:
        row = PublishJob(
            user_id=post.user_id,
            post_id=post.id,
            platform=post.platform,
            status=status,
            scheduled_at=scheduled_at,
            error_message=error_message,
        )
        db.add(row)
    else:
        row.status = status
        if scheduled_at is not None:
            row.scheduled_at = scheduled_at
        row.error_message = error_message
    now = datetime.utcnow()
    if attempted:
        row.attempted_at = now
    if completed:
        row.completed_at = now


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


def _run_agent_workflow(
    db: Session,
    user_id: str,
    payload: GenerateRequest,
) -> tuple[AgentRun, list[ResearchItem], list[ContentPlan], list[GeneratedPost]]:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    platforms = payload.platforms or ["linkedin", "twitter", "facebook", "instagram", "blog_summary"]
    profile_context = (
        f"Business={payload.business_name}; Niche={payload.niche}; Audience={payload.audience}; "
        f"Tone={payload.tone}; Region={payload.region}; Platforms={','.join(platforms)}"
    )

    run = AgentRun(
        user_id=user_id,
        business_name=payload.business_name.strip(),
        niche=payload.niche.strip(),
        audience=payload.audience.strip(),
        tone=payload.tone.strip(),
        region=payload.region.strip(),
        platforms_csv=",".join(platforms),
        language_pref=payload.language_pref,
        source_content=content,
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        research_items = collect_research_items(
            db=db,
            user_id=user_id,
            run_id=run.id,
            business_name=payload.business_name,
            niche=payload.niche,
            region=payload.region,
            audience=payload.audience,
        )
        plans = create_content_plans(
            db=db,
            user_id=user_id,
            run_id=run.id,
            platforms=platforms,
            language_pref=payload.language_pref,
            timezone_name=settings.timezone,
            research_items=research_items,
            posts_per_week=3,
        )

        research_summary = "\n".join(
            [f"- {x.title}: {x.snippet[:180]}" for x in research_items[:3] if x.title]
        )
        source_text = f"{content}\n\nResearch highlights:\n{research_summary}".strip()
        outputs = generate_platform_posts(
            content=source_text,
            platforms=platforms,
            language_pref=payload.language_pref,
            profile_context=profile_context,
        )
        created_posts: list[GeneratedPost] = []
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
            created_posts.append(row)

        db.commit()
        for row in created_posts:
            db.refresh(row)
            _ensure_approval_request(db, user_id, row.id)
            _touch_publish_job(db, row, status="draft")
        db.commit()

        run.status = "completed"
        run.completed_at = datetime.utcnow()
        run.error_text = ""
        db.commit()
        db.refresh(run)
        return run, research_items, plans, created_posts
    except Exception as exc:
        run.status = "failed"
        run.error_text = str(exc)
        run.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(run)
        raise


@app.post("/api/generate", response_model=GenerateResponse)
def generate_content(
    payload: GenerateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> GenerateResponse:
    _, _, _, created = _run_agent_workflow(db=db, user_id=user_id, payload=payload)
    return GenerateResponse(drafts=[_serialize_post(row) for row in created])


@app.post("/api/agent/run", response_model=AgentRunResponse)
def agent_run(
    payload: GenerateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AgentRunResponse:
    run, research_items, plans, created = _run_agent_workflow(db=db, user_id=user_id, payload=payload)
    return AgentRunResponse(
        run_id=run.id,
        drafts=[_serialize_post(x) for x in created],
        research_items=[_serialize_research(x) for x in research_items],
        content_plans=[_serialize_plan(x) for x in plans],
    )


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


@app.get("/api/research", response_model=list[ResearchItemResponse])
def get_research(
    limit: int = Query(default=30, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[ResearchItemResponse]:
    rows = (
        db.query(ResearchItem)
        .filter(ResearchItem.user_id == user_id)
        .order_by(ResearchItem.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_serialize_research(r) for r in rows]


@app.get("/api/content-plans", response_model=list[ContentPlanResponse])
def get_content_plans(
    run_id: int | None = Query(default=None),
    limit: int = Query(default=60, ge=1, le=200),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[ContentPlanResponse]:
    q = db.query(ContentPlan).filter(ContentPlan.user_id == user_id)
    if run_id:
        q = q.filter(ContentPlan.run_id == run_id)
    rows = q.order_by(ContentPlan.created_at.desc()).limit(limit).all()
    return [_serialize_plan(r) for r in rows]


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
    approval = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.user_id == user_id, ApprovalRequest.post_id == post.id)
        .first()
    )
    if not approval:
        approval = ApprovalRequest(user_id=user_id, post_id=post.id, status="pending", requested_at=datetime.utcnow())
        db.add(approval)
    if payload.status == "approved":
        approval.status = "approved"
        approval.resolved_at = datetime.utcnow()
        approval.resolution_note = "Approved from dashboard"
    elif payload.status == "rejected":
        approval.status = "rejected"
        approval.resolved_at = datetime.utcnow()
        approval.resolution_note = "Rejected from dashboard"
    else:
        approval.status = "pending"
        approval.resolved_at = None
        approval.resolution_note = ""
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
    _touch_publish_job(db, post, status="scheduled", scheduled_at=post.scheduled_at)
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
    if post.platform == "twitter":
        _touch_publish_job(
            db,
            post,
            status="failed",
            error_message="Twitter free mode requires manual publish",
            attempted=True,
        )
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Twitter is on free mode. Use manual publish from the dashboard.",
        )

    try:
        media = list_post_media(db, user_id, post.id)
        refresh_media_signed_urls(db, media)
        result = publish_to_linkedin(db, user_id, content, media_items=media)
        post.status = PostStatus.posted.value
        post.posted_at = datetime.utcnow()
        post.external_post_id = result.get("external_post_id", "")
        post.last_error = ""
        _touch_publish_job(db, post, status="posted", attempted=True, completed=True, error_message="")
    except Exception as exc:
        post.status = PostStatus.failed.value
        post.last_error = str(exc)
        _touch_publish_job(db, post, status="failed", attempted=True, error_message=str(exc))
        db.commit()
        db.refresh(post)
        raise HTTPException(status_code=500, detail=f"Publish failed: {exc}") from exc

    db.commit()
    db.refresh(post)
    return _serialize_post(post)


@app.post("/api/posts/{post_id}/manual-publish", response_model=DraftPost)
def manual_publish_post(
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
    if post.platform != "twitter":
        raise HTTPException(status_code=400, detail="Manual publish endpoint is only for Twitter")
    if post.status not in [PostStatus.approved.value, PostStatus.scheduled.value, PostStatus.failed.value]:
        raise HTTPException(status_code=400, detail="Post must be approved or scheduled before publishing")

    post.status = PostStatus.posted.value
    post.posted_at = datetime.utcnow()
    post.external_post_id = "manual://twitter-intent"
    post.last_error = ""
    _touch_publish_job(db, post, status="posted", attempted=True, completed=True, error_message="")
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
        SocialAccountResponse(platform="instagram", connected=False, account_name=None),
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


@app.get("/api/facebook/connect/start", response_model=LinkedInConnectStartResponse)
def facebook_connect_start(
    user_id: str = Depends(get_current_user_id),
) -> LinkedInConnectStartResponse:
    _ = user_id
    raise HTTPException(status_code=501, detail="Facebook credentials not configured yet")


@app.get("/api/instagram/connect/start", response_model=LinkedInConnectStartResponse)
def instagram_connect_start(
    user_id: str = Depends(get_current_user_id),
) -> LinkedInConnectStartResponse:
    _ = user_id
    raise HTTPException(status_code=501, detail="Instagram credentials not configured yet")


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
