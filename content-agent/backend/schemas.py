from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    content: str = Field(..., min_length=1)


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