from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session

from backend.ai_service import generate_platform_posts
from backend.analytics_service import aggregate_metrics, record_publish_metric, resolve_post_client_id
from backend.auth import get_current_user_id
from backend.canva_service import create_canva_authorization_url, handle_canva_callback
from backend.database import SessionLocal, get_db, init_db
from backend.db_models import (
    AgentRun,
    ApprovalRequest,
    ClientPayment,
    ClientPerformanceMetric,
    ClientProfile,
    ContentPlan,
    GeneratedPost,
    MediaAsset,
    PlanClientLink,
    PostClientLink,
    PostStatus,
    PublishJob,
    ResearchItem,
    SocialAccount,
)
from backend.instagram_service import connect_instagram_from_settings, publish_to_instagram
from backend.linkedin_service import create_linkedin_authorization_url, handle_linkedin_callback, publish_to_linkedin
from backend.facebook_service import connect_facebook_from_settings, publish_to_facebook
from backend.image_service import generate_plan_image, generate_post_visual_from_template, list_canva_templates
from backend.media_service import list_post_media, refresh_media_signed_urls, upload_media_base64
from backend.planning_service import create_content_plans
from backend.research_service import collect_research_items
from backend.scheduler import create_scheduler
from backend.twitter_service import create_twitter_authorization_url, handle_twitter_callback
from backend.whatsapp_service import request_whatsapp_approval, resolve_whatsapp_approval, verify_webhook
from backend.schemas import (
    AgentRunResponse,
    AnalyticsOverviewResponse,
    AnalyticsPoint,
    CanvaTemplateResponse,
    ClientOnboardingActionResponse,
    ClientOnboardingStatusResponse,
    ClientOnboardingStep,
    ClientIntakeRequest,
    ClientIntakeUpdateRequest,
    ClientResponse,
    ContentCalendarGenerateRequest,
    ContentCalendarGenerateResponse,
    ContentPlanResponse,
    DashboardOverviewResponse,
    GenerateRequest,
    GenerateResponse,
    GenerateVisualRequest,
    DraftPost,
    HistoryResponse,
    LinkedInConnectStartResponse,
    MediaAssetResponse,
    PaymentCreateRequest,
    PaymentResponse,
    PaymentUpdateRequest,
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
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


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


def _ensure_client(db: Session, user_id: str, client_id: int) -> ClientProfile:
    row = db.query(ClientProfile).filter(ClientProfile.id == client_id, ClientProfile.user_id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Client not found")
    return row


def _apply_payment_auto_pause(db: Session, user_id: str) -> None:
    now = datetime.utcnow()
    clients = db.query(ClientProfile).filter(ClientProfile.user_id == user_id).all()
    if not clients:
        return

    payment_rows = db.query(ClientPayment).filter(ClientPayment.user_id == user_id).all()
    by_client: dict[int, list[ClientPayment]] = {}
    for row in payment_rows:
        by_client.setdefault(row.client_id, []).append(row)

    changed = False
    for client in clients:
        rows = by_client.get(client.id, [])
        should_pause = False
        for payment in rows:
            status = (payment.subscription_status or "").strip().lower()
            if not payment.auto_pause_if_unpaid:
                continue
            if status in {"unpaid", "paused", "cancelled"}:
                should_pause = True
                break
            if status == "past_due" and payment.due_date and payment.due_date <= now:
                should_pause = True
                break
        if client.service_paused != should_pause:
            client.service_paused = should_pause
            changed = True

    if changed:
        db.commit()


def _upsert_post_client_link(db: Session, user_id: str, client_id: int, post_id: int) -> None:
    row = (
        db.query(PostClientLink)
        .filter(PostClientLink.user_id == user_id, PostClientLink.post_id == post_id)
        .first()
    )
    if row:
        row.client_id = client_id
        return
    db.add(PostClientLink(user_id=user_id, client_id=client_id, post_id=post_id))


def _upsert_plan_client_link(db: Session, user_id: str, client_id: int, plan_id: int) -> None:
    row = (
        db.query(PlanClientLink)
        .filter(PlanClientLink.user_id == user_id, PlanClientLink.plan_id == plan_id)
        .first()
    )
    if row:
        row.client_id = client_id
        return
    db.add(PlanClientLink(user_id=user_id, client_id=client_id, plan_id=plan_id))


def _client_connected_accounts(db: Session, user_id: str) -> list[str]:
    rows = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform.in_(["linkedin", "instagram", "facebook"]))
        .all()
    )
    return sorted({r.platform for r in rows})


def _next_scheduled_for_client(db: Session, user_id: str, client_id: int) -> datetime | None:
    row = (
        db.query(GeneratedPost)
        .join(PostClientLink, PostClientLink.post_id == GeneratedPost.id)
        .filter(
            PostClientLink.user_id == user_id,
            PostClientLink.client_id == client_id,
            GeneratedPost.status == PostStatus.scheduled.value,
            GeneratedPost.scheduled_at.isnot(None),
        )
        .order_by(GeneratedPost.scheduled_at.asc())
        .first()
    )
    return row.scheduled_at if row else None


def _client_engagement(db: Session, user_id: str, client_id: int) -> tuple[int, int, int, int]:
    rows = (
        db.query(ClientPerformanceMetric)
        .filter(ClientPerformanceMetric.user_id == user_id, ClientPerformanceMetric.client_id == client_id)
        .all()
    )
    likes = sum(int(x.likes or 0) for x in rows)
    shares = sum(int(x.shares or 0) for x in rows)
    clicks = sum(int(x.clicks or 0) for x in rows)
    followers = sum(int(x.follower_growth or 0) for x in rows)
    return likes, shares, clicks, followers


def _build_onboarding_status(db: Session, user_id: str, client: ClientProfile) -> ClientOnboardingStatusResponse:
    questionnaire_done = all(
        [
            client.business_name.strip(),
            client.industry.strip(),
            client.website.strip(),
            client.brand_voice.strip(),
            client.keywords.strip(),
            client.topics_to_avoid.strip(),
            client.target_audience.strip(),
        ]
    )
    brand_profile_done = all(
        [
            client.brand_voice.strip(),
            client.keywords.strip(),
            client.target_audience.strip(),
        ]
    )
    connected = len(_client_connected_accounts(db, user_id)) > 0

    steps = [
        ClientOnboardingStep(key="questionnaire", title="Questionnaire", done=questionnaire_done),
        ClientOnboardingStep(key="brand_profile", title="Brand Profile", done=brand_profile_done),
        ClientOnboardingStep(key="social_accounts", title="Connect Social Accounts", done=connected),
    ]
    status = "completed" if all(step.done for step in steps) else "in_progress"
    return ClientOnboardingStatusResponse(client_id=client.id, status=status, steps=steps)


def _serialize_client(db: Session, user_id: str, row: ClientProfile) -> ClientResponse:
    likes, shares, clicks, followers = _client_engagement(db, user_id, row.id)
    onboarding = _build_onboarding_status(db, user_id, row)
    if row.onboarding_status != onboarding.status:
        row.onboarding_status = onboarding.status
        db.commit()
        db.refresh(row)
    return ClientResponse(
        id=row.id,
        business_name=row.business_name,
        industry=row.industry,
        social_handles=row.social_handles,
        website=row.website,
        brand_voice=row.brand_voice,
        keywords=row.keywords,
        topics_to_avoid=row.topics_to_avoid,
        target_audience=row.target_audience,
        whatsapp_number=row.whatsapp_number,
        logo_url=row.logo_url,
        onboarding_status=row.onboarding_status,
        service_paused=row.service_paused,
        notes=row.notes,
        next_scheduled_post=_next_scheduled_for_client(db, user_id, row.id),
        connected_accounts=_client_connected_accounts(db, user_id),
        engagement_likes=likes,
        engagement_shares=shares,
        engagement_clicks=clicks,
        follower_growth=followers,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _serialize_payment(db: Session, payment: ClientPayment) -> PaymentResponse:
    client = db.query(ClientProfile).filter(ClientProfile.id == payment.client_id).first()
    return PaymentResponse(
        id=payment.id,
        client_id=payment.client_id,
        client_name=client.business_name if client else "Unknown",
        plan_name=payment.plan_name,
        subscription_status=payment.subscription_status,
        amount=payment.amount,
        currency=payment.currency,
        due_date=payment.due_date,
        last_paid_at=payment.last_paid_at,
        auto_pause_if_unpaid=payment.auto_pause_if_unpaid,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


def _assert_post_client_active(db: Session, user_id: str, post_id: int) -> None:
    client_id = resolve_post_client_id(db, user_id, post_id)
    if not client_id:
        return
    client = db.query(ClientProfile).filter(ClientProfile.id == client_id, ClientProfile.user_id == user_id).first()
    if client and client.service_paused:
        raise HTTPException(status_code=403, detail="Service paused for this client due to unpaid subscription")


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

    _apply_payment_auto_pause(db, user_id)

    client: ClientProfile | None = None
    if payload.client_id:
        client = _ensure_client(db, user_id, payload.client_id)
        if client.service_paused:
            raise HTTPException(status_code=403, detail="Client service is paused due to unpaid subscription")

    platforms = payload.platforms or ["linkedin", "instagram", "facebook"]
    profile_context = (
        f"Business={payload.business_name or (client.business_name if client else '')}; "
        f"Niche={payload.niche or (client.industry if client else '')}; "
        f"Audience={payload.audience or (client.target_audience if client else '')}; "
        f"Tone={payload.tone or (client.brand_voice if client else '')}; "
        f"Region={payload.region}; Platforms={','.join(platforms)}"
    )

    run = AgentRun(
        user_id=user_id,
        business_name=(payload.business_name.strip() or (client.business_name if client else "")),
        niche=(payload.niche.strip() or (client.industry if client else "")),
        audience=(payload.audience.strip() or (client.target_audience if client else "")),
        tone=(payload.tone.strip() or (client.brand_voice if client else "")),
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
            business_name=run.business_name,
            niche=run.niche,
            region=payload.region,
            audience=run.audience,
        )
        plans = create_content_plans(
            db=db,
            user_id=user_id,
            run_id=run.id,
            platforms=platforms,
            language_pref=payload.language_pref,
            timezone_name=settings.timezone,
            research_items=research_items,
            business_name=run.business_name,
            niche=run.niche,
            audience=run.audience,
            tone=run.tone,
            region=payload.region,
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
            if client:
                _upsert_post_client_link(db, user_id, client.id, row.id)
        if client:
            for plan in plans:
                _upsert_plan_client_link(db, user_id, client.id, plan.id)
        db.commit()

        if settings.auto_generate_plan_images_on_run:
            # Optional mode: auto-generate one visual per platform and attach it to matching draft.
            posts_by_platform: dict[str, GeneratedPost] = {}
            for row in created_posts:
                posts_by_platform.setdefault(row.platform, row)
            plans_by_platform: dict[str, ContentPlan] = {}
            for plan in plans:
                plans_by_platform.setdefault(plan.platform, plan)
            for platform, post in posts_by_platform.items():
                plan = plans_by_platform.get(platform)
                if not plan:
                    continue
                try:
                    generate_plan_image(
                        db=db,
                        user_id=user_id,
                        plan_id=plan.id,
                        business_name=run.business_name,
                        source_text=content,
                        attach_post_id=post.id,
                    )
                except Exception:
                    # Do not fail draft creation if visual generation has a provider/runtime issue.
                    continue

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


@app.get("/api/dashboard/overview", response_model=DashboardOverviewResponse)
def dashboard_overview(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> DashboardOverviewResponse:
    _apply_payment_auto_pause(db, user_id)

    total_clients = db.query(ClientProfile).filter(ClientProfile.user_id == user_id).count()
    scheduled_posts = db.query(GeneratedPost).filter(
        GeneratedPost.user_id == user_id,
        GeneratedPost.status == PostStatus.scheduled.value,
    ).count()
    pending_approvals = db.query(ApprovalRequest).filter(
        ApprovalRequest.user_id == user_id,
        ApprovalRequest.status == "pending",
    ).count()
    metric_rows = db.query(ClientPerformanceMetric).filter(ClientPerformanceMetric.user_id == user_id).all()
    engagement_total = sum(int(x.likes or 0) + int(x.shares or 0) + int(x.clicks or 0) + int(x.comments or 0) for x in metric_rows)
    payment_rows = db.query(ClientPayment).filter(ClientPayment.user_id == user_id).all()
    revenue_total = sum(float(x.amount or 0.0) for x in payment_rows if x.subscription_status == "active")

    return DashboardOverviewResponse(
        total_clients=total_clients,
        scheduled_posts=scheduled_posts,
        engagement_total=engagement_total,
        revenue_total=round(revenue_total, 2),
        pending_approvals=pending_approvals,
    )


@app.post("/api/content-calendar/generate", response_model=ContentCalendarGenerateResponse)
def generate_content_calendar(
    payload: ContentCalendarGenerateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ContentCalendarGenerateResponse:
    _apply_payment_auto_pause(db, user_id)

    client: ClientProfile | None = None
    if payload.client_id:
        client = _ensure_client(db, user_id, payload.client_id)
        if client.service_paused:
            raise HTTPException(status_code=403, detail="Client service is paused due to unpaid subscription")

    platforms = [p for p in payload.platforms if p in {"linkedin", "instagram", "facebook", "twitter", "blog_summary"}]
    if not platforms:
        platforms = ["linkedin", "instagram", "facebook"]

    run = AgentRun(
        user_id=user_id,
        business_name=client.business_name if client else "",
        niche=client.industry if client else "",
        audience=client.target_audience if client else "",
        tone=client.brand_voice if client else "",
        region="",
        platforms_csv=",".join(platforms),
        language_pref=payload.language_pref,
        source_content=payload.content_seed.strip(),
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    outputs = generate_platform_posts(
        content=payload.content_seed,
        platforms=platforms,
        language_pref=payload.language_pref,
        profile_context=f"Business={(client.business_name if client else '')}; Industry={(client.industry if client else '')}",
    )
    plans = create_content_plans(
        db=db,
        user_id=user_id,
        run_id=run.id,
        platforms=platforms,
        language_pref=payload.language_pref,
        timezone_name=settings.timezone,
        research_items=[],
        business_name=client.business_name if client else "",
        niche=client.industry if client else "",
        audience=client.target_audience if client else "",
        tone=client.brand_voice if client else "",
        region="",
        posts_per_week=payload.days,
    )

    created_posts: list[GeneratedPost] = []
    for plan in plans:
        base_text = outputs.get(plan.platform, "")
        text = f"{base_text}\n\nDaily focus: {plan.theme}".strip()
        post = GeneratedPost(
            user_id=user_id,
            platform=plan.platform,
            input_content=payload.content_seed,
            generated_text=text,
            edited_text="",
            status=PostStatus.scheduled.value,
            scheduled_at=plan.planned_for,
        )
        db.add(post)
        created_posts.append(post)

    db.commit()
    for post in created_posts:
        db.refresh(post)
        _ensure_approval_request(db, user_id, post.id)
        _touch_publish_job(db, post, status="scheduled", scheduled_at=post.scheduled_at)
        if client:
            _upsert_post_client_link(db, user_id, client.id, post.id)
    if client:
        for plan in plans:
            _upsert_plan_client_link(db, user_id, client.id, plan.id)

    run.status = "completed"
    run.completed_at = datetime.utcnow()
    run.error_text = ""
    db.commit()

    return ContentCalendarGenerateResponse(
        created_posts=len(created_posts),
        created_plans=len(plans),
        message="7-day content calendar generated and scheduled.",
    )


@app.get("/api/analytics/overview", response_model=AnalyticsOverviewResponse)
def analytics_overview(
    days: int = Query(default=14, ge=1, le=90),
    client_id: int | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AnalyticsOverviewResponse:
    if client_id:
        _ensure_client(db, user_id, client_id)
    totals, series_rows = aggregate_metrics(db, user_id=user_id, days=days, client_id=client_id)
    series = [AnalyticsPoint(**row) for row in series_rows]
    return AnalyticsOverviewResponse(totals=totals, series=series)


@app.get("/api/clients", response_model=list[ClientResponse])
def list_clients(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[ClientResponse]:
    _apply_payment_auto_pause(db, user_id)
    rows = db.query(ClientProfile).filter(ClientProfile.user_id == user_id).order_by(ClientProfile.created_at.desc()).all()
    return [_serialize_client(db, user_id, row) for row in rows]


@app.post("/api/clients", response_model=ClientResponse)
def create_client(
    payload: ClientIntakeRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ClientResponse:
    row = ClientProfile(
        user_id=user_id,
        business_name=payload.business_name.strip(),
        industry=payload.industry.strip(),
        social_handles=payload.social_handles.strip(),
        website=payload.website.strip(),
        brand_voice=payload.brand_voice.strip(),
        keywords=payload.keywords.strip(),
        topics_to_avoid=payload.topics_to_avoid.strip(),
        target_audience=payload.target_audience.strip(),
        whatsapp_number=payload.whatsapp_number.strip(),
        logo_url=payload.logo_url.strip(),
        notes=payload.notes.strip(),
        onboarding_status="pending",
        service_paused=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_client(db, user_id, row)


@app.patch("/api/clients/{client_id}", response_model=ClientResponse)
def update_client(
    client_id: int,
    payload: ClientIntakeUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ClientResponse:
    row = _ensure_client(db, user_id, client_id)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if isinstance(value, str):
            setattr(row, key, value.strip())
        else:
            setattr(row, key, value)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _serialize_client(db, user_id, row)


@app.get("/api/clients/{client_id}/onboarding", response_model=ClientOnboardingStatusResponse)
def get_client_onboarding(
    client_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ClientOnboardingStatusResponse:
    row = _ensure_client(db, user_id, client_id)
    return _build_onboarding_status(db, user_id, row)


@app.post("/api/clients/{client_id}/onboarding/complete", response_model=ClientOnboardingActionResponse)
def complete_client_onboarding(
    client_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ClientOnboardingActionResponse:
    row = _ensure_client(db, user_id, client_id)
    onboarding = _build_onboarding_status(db, user_id, row)
    row.onboarding_status = onboarding.status
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return ClientOnboardingActionResponse(client=_serialize_client(db, user_id, row), onboarding=onboarding)


@app.get("/api/payments", response_model=list[PaymentResponse])
def list_payments(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[PaymentResponse]:
    _apply_payment_auto_pause(db, user_id)
    rows = db.query(ClientPayment).filter(ClientPayment.user_id == user_id).order_by(ClientPayment.created_at.desc()).all()
    return [_serialize_payment(db, row) for row in rows]


@app.post("/api/payments", response_model=PaymentResponse)
def create_payment(
    payload: PaymentCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> PaymentResponse:
    _ensure_client(db, user_id, payload.client_id)
    row = ClientPayment(
        user_id=user_id,
        client_id=payload.client_id,
        plan_name=payload.plan_name.strip(),
        subscription_status=payload.subscription_status,
        amount=payload.amount,
        currency=payload.currency.strip().upper() or "USD",
        due_date=payload.due_date,
        last_paid_at=payload.last_paid_at,
        auto_pause_if_unpaid=payload.auto_pause_if_unpaid,
    )
    db.add(row)
    db.commit()
    _apply_payment_auto_pause(db, user_id)
    db.refresh(row)
    return _serialize_payment(db, row)


@app.patch("/api/payments/{payment_id}", response_model=PaymentResponse)
def update_payment(
    payment_id: int,
    payload: PaymentUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> PaymentResponse:
    row = db.query(ClientPayment).filter(ClientPayment.id == payment_id, ClientPayment.user_id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Payment record not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if isinstance(value, str):
            setattr(row, key, value.strip())
        else:
            setattr(row, key, value)
    row.updated_at = datetime.utcnow()
    db.commit()
    _apply_payment_auto_pause(db, user_id)
    db.refresh(row)
    return _serialize_payment(db, row)


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


@app.post("/api/content-plans/{plan_id}/generate-image", response_model=ContentPlanResponse)
def generate_content_plan_image(
    plan_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ContentPlanResponse:
    plan = db.query(ContentPlan).filter(ContentPlan.id == plan_id, ContentPlan.user_id == user_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Content plan not found")

    run = db.query(AgentRun).filter(AgentRun.id == plan.run_id, AgentRun.user_id == user_id).first()
    business_name = run.business_name if run else ""
    source_text = run.source_content if run else ""
    draft_for_platform = (
        db.query(GeneratedPost)
        .filter(
            GeneratedPost.user_id == user_id,
            GeneratedPost.platform == plan.platform,
            GeneratedPost.status != PostStatus.posted.value,
        )
        .order_by(GeneratedPost.created_at.desc())
        .first()
    )
    try:
        updated = generate_plan_image(
            db=db,
            user_id=user_id,
            plan_id=plan_id,
            business_name=business_name,
            source_text=source_text,
            attach_post_id=draft_for_platform.id if draft_for_platform else None,
            strict_ai=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Image generation failed: {exc}") from exc
    return _serialize_plan(updated)


@app.get("/api/canva/templates", response_model=list[CanvaTemplateResponse])
def get_canva_templates(
    user_id: str = Depends(get_current_user_id),
) -> list[CanvaTemplateResponse]:
    _ = user_id
    return [CanvaTemplateResponse(**item) for item in list_canva_templates()]


@app.post("/api/posts/{post_id}/generate-visual", response_model=MediaAssetResponse)
def generate_post_visual(
    post_id: int,
    payload: GenerateVisualRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> MediaAssetResponse:
    try:
        media = generate_post_visual_from_template(
            db=db,
            user_id=user_id,
            post_id=post_id,
            template_id=payload.template_id,
            caption_hint=payload.caption_hint,
            brand_name=payload.brand_name,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Canva visual generation failed: {exc}") from exc
    return _serialize_media(media)


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
    _assert_post_client_active(db, user_id, post_id)

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

    _assert_post_client_active(db, user_id, post_id)

    post = db.query(GeneratedPost).filter(GeneratedPost.id == post_id, GeneratedPost.user_id == user_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.platform not in ["linkedin", "instagram", "twitter", "facebook"]:
        raise HTTPException(status_code=400, detail="Publishing is enabled for LinkedIn, Instagram, Twitter, and Facebook only")

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
        if post.platform == "linkedin" and not media:
            raise RuntimeError("Attach or generate at least one image before LinkedIn publish")
        if post.platform == "instagram" and not any(x.mime_type.startswith("image/") for x in media):
            raise RuntimeError("Instagram publish requires at least one image")
        if post.platform == "linkedin":
            result = publish_to_linkedin(db, user_id, content, media_items=media)
        elif post.platform == "instagram":
            result = publish_to_instagram(db, user_id, content, media_items=media)
        elif post.platform == "facebook":
            result = publish_to_facebook(db, user_id, content, media_items=media)
        else:
            raise RuntimeError("Unsupported automatic publish platform")
        post.status = PostStatus.posted.value
        post.posted_at = datetime.utcnow()
        post.external_post_id = result.get("external_post_id", "")
        post.last_error = ""
        _touch_publish_job(db, post, status="posted", attempted=True, completed=True, error_message="")
        record_publish_metric(
            db,
            user_id=user_id,
            post_id=post.id,
            platform=post.platform,
            posted_at=post.posted_at,
        )
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


@app.post("/api/posts/{post_id}/request-approval")
def request_post_approval(
    post_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, str | int]:
    post = db.query(GeneratedPost).filter(GeneratedPost.id == post_id, GeneratedPost.user_id == user_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    try:
        result = request_whatsapp_approval(db=db, post=post)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"WhatsApp approval failed: {exc}") from exc
    sent_to = int(result.get("sent_to", 0))
    failed_count = int(result.get("failed_count", 0))
    message = f"Approval request sent to {sent_to} recipient(s)"
    if failed_count > 0:
        message += f". {failed_count} recipient(s) failed (not allowed/test-mode or temporary Meta issue)."
    return {
        "message": message,
        "sent_to": sent_to,
        "failed_count": failed_count,
    }


@app.get("/api/whatsapp/approval/resolve")
def resolve_whatsapp_approval_link(
    token: str = Query(..., min_length=20),
    action: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, str | int]:
    try:
        result = resolve_whatsapp_approval(db=db, token=token, action=action)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.get("/api/whatsapp/webhook")
def whatsapp_webhook_verify(
    mode: str | None = Query(default=None, alias="hub.mode"),
    token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    try:
        verified = verify_webhook(mode=mode, verify_token=token, challenge=challenge)
    except Exception as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return PlainTextResponse(content=verified)


@app.post("/api/whatsapp/webhook")
def whatsapp_webhook_events(payload: dict) -> dict[str, str]:
    _ = payload
    return {"status": "received"}


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
    record_publish_metric(
        db,
        user_id=user_id,
        post_id=post.id,
        platform=post.platform,
        posted_at=post.posted_at,
    )
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
    instagram = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "instagram")
        .first()
    )
    twitter = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "twitter")
        .first()
    )
    canva = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "canva")
        .first()
    )
    facebook = (
        db.query(SocialAccount)
        .filter(SocialAccount.user_id == user_id, SocialAccount.platform == "facebook")
        .first()
    )

    return [
        SocialAccountResponse(
            platform="linkedin",
            connected=linkedin is not None,
            account_name=linkedin.account_name if linkedin else None,
        ),
        SocialAccountResponse(
            platform="instagram",
            connected=instagram is not None,
            account_name=instagram.account_name if instagram else None,
        ),
        SocialAccountResponse(
            platform="twitter",
            connected=twitter is not None,
            account_name=twitter.account_name if twitter else None,
        ),
        SocialAccountResponse(
            platform="canva",
            connected=canva is not None,
            account_name=canva.account_name if canva else None,
        ),
        SocialAccountResponse(
            platform="facebook",
            connected=facebook is not None,
            account_name=facebook.account_name if facebook else None,
        ),
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
    db: Session = Depends(get_db),
) -> LinkedInConnectStartResponse:
    try:
        connect_facebook_from_settings(db, user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Facebook connect failed: {exc}") from exc
    redirect_base = settings.frontend_url.rstrip("/") if settings.frontend_url else ""
    success_url = f"{redirect_base}/index.html?facebook=connected" if redirect_base else "/index.html?facebook=connected"
    return LinkedInConnectStartResponse(authorization_url=success_url)


@app.get("/api/instagram/connect/start", response_model=LinkedInConnectStartResponse)
def instagram_connect_start(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> LinkedInConnectStartResponse:
    try:
        connect_instagram_from_settings(db, user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Instagram connect failed: {exc}") from exc
    redirect_base = settings.frontend_url.rstrip("/") if settings.frontend_url else ""
    success_url = f"{redirect_base}/index.html?instagram=connected" if redirect_base else "/index.html?instagram=connected"
    return LinkedInConnectStartResponse(authorization_url=success_url)


@app.get("/api/canva/connect/start", response_model=LinkedInConnectStartResponse)
def canva_connect_start(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> LinkedInConnectStartResponse:
    url = create_canva_authorization_url(db, user_id)
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


@app.get("/api/canva/callback")
def canva_connect_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    redirect_base = settings.frontend_url.rstrip("/") if settings.frontend_url else ""
    success_url = f"{redirect_base}/index.html?canva=connected" if redirect_base else "/index.html?canva=connected"
    if error:
        description = (error_description or "").replace("+", " ")
        message = f"Canva OAuth error: {error}. {description}".strip()
        error_url = f"{redirect_base}/index.html?canva=error&message={message}" if redirect_base else f"/index.html?canva=error&message={message}"
        return RedirectResponse(url=error_url)

    if not code or not state:
        message = "Canva callback missing code/state. Check app redirect URI and scopes."
        error_url = f"{redirect_base}/index.html?canva=error&message={message}" if redirect_base else f"/index.html?canva=error&message={message}"
        return RedirectResponse(url=error_url)

    try:
        handle_canva_callback(db, code, state)
    except Exception as exc:
        error_url = f"{redirect_base}/index.html?canva=error&message={str(exc)}" if redirect_base else f"/index.html?canva=error&message={str(exc)}"
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


def _frontend_file(name: str) -> FileResponse:
    target = FRONTEND_DIR / name
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Frontend file not found")
    return FileResponse(str(target))


@app.get("/")
def frontend_root() -> FileResponse:
    return _frontend_file("index.html")


@app.get("/index.html")
def frontend_index() -> FileResponse:
    return _frontend_file("index.html")


@app.get("/style.css")
def frontend_style() -> FileResponse:
    return _frontend_file("style.css")


@app.get("/script.js")
def frontend_script() -> FileResponse:
    return _frontend_file("script.js")


@app.get("/config.js")
def frontend_config() -> FileResponse:
    return _frontend_file("config.js")
