from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    content: str = Field(..., min_length=1)
    client_id: int | None = None
    business_name: str = ""
    niche: str = ""
    audience: str = ""
    tone: str = ""
    region: str = ""
    platforms: list[str] = Field(default_factory=list)
    language_pref: Literal["english", "urdu", "english_urdu"] = "english_urdu"


class DraftPost(BaseModel):
    id: int
    platform: str
    input_content: str
    generated_text: str
    edited_text: str
    status: str
    scheduled_at: datetime | None
    posted_at: datetime | None
    last_error: str
    created_at: datetime


class GenerateResponse(BaseModel):
    drafts: list[DraftPost]


class MediaAssetResponse(BaseModel):
    id: int
    post_id: int
    platform: str
    file_name: str
    mime_type: str
    file_size: int
    file_url: str
    platform_asset_id: str
    upload_status: str
    last_error: str
    created_at: datetime


class UploadMediaRequest(BaseModel):
    post_id: int
    file_name: str
    mime_type: str
    content_base64: str


class UpdatePostRequest(BaseModel):
    edited_text: str


class UpdateStatusRequest(BaseModel):
    status: Literal["approved", "rejected", "draft"]


class ScheduleRequest(BaseModel):
    scheduled_at: datetime


class PublishNowRequest(BaseModel):
    confirm: bool = False


class SocialAccountResponse(BaseModel):
    platform: str
    connected: bool
    account_name: str | None = None


class LinkedInConnectStartResponse(BaseModel):
    authorization_url: str


class HistoryResponse(BaseModel):
    posts: list[DraftPost]


class ResearchItemResponse(BaseModel):
    id: int
    source: str
    title: str
    url: str
    snippet: str
    published_at: datetime | None
    created_at: datetime


class ContentPlanResponse(BaseModel):
    id: int
    platform: str
    language_pref: str
    planned_for: datetime | None
    status: str
    theme: str
    post_angle: str
    image_prompt: str
    image_url: str
    created_at: datetime


class AgentRunResponse(BaseModel):
    run_id: int
    drafts: list[DraftPost]
    research_items: list[ResearchItemResponse]
    content_plans: list[ContentPlanResponse]


class ClientIntakeRequest(BaseModel):
    business_name: str = Field(..., min_length=1)
    industry: str = ""
    social_handles: str = ""
    website: str = ""
    brand_voice: str = ""
    keywords: str = ""
    topics_to_avoid: str = ""
    target_audience: str = ""
    whatsapp_number: str = ""
    logo_url: str = ""
    notes: str = ""


class ClientIntakeUpdateRequest(BaseModel):
    business_name: str | None = None
    industry: str | None = None
    social_handles: str | None = None
    website: str | None = None
    brand_voice: str | None = None
    keywords: str | None = None
    topics_to_avoid: str | None = None
    target_audience: str | None = None
    whatsapp_number: str | None = None
    logo_url: str | None = None
    service_paused: bool | None = None
    notes: str | None = None


class ClientResponse(BaseModel):
    id: int
    business_name: str
    industry: str
    social_handles: str
    website: str
    brand_voice: str
    keywords: str
    topics_to_avoid: str
    target_audience: str
    whatsapp_number: str
    logo_url: str
    onboarding_status: str
    service_paused: bool
    notes: str
    next_scheduled_post: datetime | None = None
    connected_accounts: list[str] = Field(default_factory=list)
    engagement_likes: int = 0
    engagement_shares: int = 0
    engagement_clicks: int = 0
    follower_growth: int = 0
    created_at: datetime
    updated_at: datetime


class ClientOnboardingStep(BaseModel):
    key: str
    title: str
    done: bool


class ClientOnboardingStatusResponse(BaseModel):
    client_id: int
    status: str
    steps: list[ClientOnboardingStep]


class ClientOnboardingActionResponse(BaseModel):
    client: ClientResponse
    onboarding: ClientOnboardingStatusResponse


class PaymentCreateRequest(BaseModel):
    client_id: int
    plan_name: str = "Starter"
    subscription_status: Literal["active", "past_due", "unpaid", "paused", "cancelled"] = "active"
    amount: float = 0.0
    currency: str = "USD"
    due_date: datetime | None = None
    last_paid_at: datetime | None = None
    auto_pause_if_unpaid: bool = True


class PaymentUpdateRequest(BaseModel):
    plan_name: str | None = None
    subscription_status: Literal["active", "past_due", "unpaid", "paused", "cancelled"] | None = None
    amount: float | None = None
    currency: str | None = None
    due_date: datetime | None = None
    last_paid_at: datetime | None = None
    auto_pause_if_unpaid: bool | None = None


class PaymentResponse(BaseModel):
    id: int
    client_id: int
    client_name: str
    plan_name: str
    subscription_status: str
    amount: float
    currency: str
    due_date: datetime | None
    last_paid_at: datetime | None
    auto_pause_if_unpaid: bool
    created_at: datetime
    updated_at: datetime


class DashboardOverviewResponse(BaseModel):
    total_clients: int
    scheduled_posts: int
    engagement_total: int
    revenue_total: float
    pending_approvals: int


class AnalyticsPoint(BaseModel):
    date: str
    likes: int
    shares: int
    comments: int
    clicks: int
    follower_growth: int


class AnalyticsOverviewResponse(BaseModel):
    totals: dict[str, int]
    series: list[AnalyticsPoint]


class CanvaTemplateResponse(BaseModel):
    id: str
    name: str
    category: str
    description: str


class GenerateVisualRequest(BaseModel):
    template_id: str
    caption_hint: str = ""
    brand_name: str = ""


class ContentCalendarGenerateRequest(BaseModel):
    client_id: int | None = None
    content_seed: str = Field(..., min_length=1)
    platforms: list[str] = Field(default_factory=lambda: ["linkedin", "facebook", "instagram"])
    language_pref: Literal["english", "urdu", "english_urdu"] = "english_urdu"
    days: int = Field(default=7, ge=1, le=7)


class ContentCalendarGenerateResponse(BaseModel):
    created_posts: int
    created_plans: int
    message: str
