from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    content: str = Field(..., min_length=1)
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
