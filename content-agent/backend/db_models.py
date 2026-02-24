from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Platform(str, Enum):
    linkedin = "linkedin"
    twitter = "twitter"
    facebook = "facebook"


class PostStatus(str, Enum):
    draft = "draft"
    approved = "approved"
    rejected = "rejected"
    scheduled = "scheduled"
    posted = "posted"
    failed = "failed"


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (UniqueConstraint("user_id", "platform", name="uq_user_platform"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    platform: Mapped[str] = mapped_column(String(24), index=True)
    account_id: Mapped[str] = mapped_column(String(128))
    account_name: Mapped[str] = mapped_column(String(256), default="")
    access_token_enc: Mapped[str] = mapped_column(Text)
    refresh_token_enc: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GeneratedPost(Base):
    __tablename__ = "generated_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    platform: Mapped[str] = mapped_column(String(24), index=True)
    input_content: Mapped[str] = mapped_column(Text)
    generated_text: Mapped[str] = mapped_column(Text)
    edited_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default=PostStatus.draft.value, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    external_post_id: Mapped[str] = mapped_column(String(256), default="")
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    state_token: Mapped[str] = mapped_column(String(256), index=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("generated_posts.id"), index=True)
    platform: Mapped[str] = mapped_column(String(24), default="linkedin", index=True)
    file_name: Mapped[str] = mapped_column(String(256))
    mime_type: Mapped[str] = mapped_column(String(128))
    file_size: Mapped[int] = mapped_column(default=0)
    storage_path: Mapped[str] = mapped_column(String(512))
    file_url: Mapped[str] = mapped_column(Text, default="")
    platform_asset_id: Mapped[str] = mapped_column(String(256), default="")
    upload_status: Mapped[str] = mapped_column(String(24), default="uploaded", index=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    business_name: Mapped[str] = mapped_column(String(256), default="")
    niche: Mapped[str] = mapped_column(String(256), default="")
    audience: Mapped[str] = mapped_column(String(256), default="")
    tone: Mapped[str] = mapped_column(String(128), default="")
    region: Mapped[str] = mapped_column(String(128), default="")
    platforms_csv: Mapped[str] = mapped_column(Text, default="")
    language_pref: Mapped[str] = mapped_column(String(32), default="english_urdu")
    source_content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    error_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ResearchItem(Base):
    __tablename__ = "research_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ContentPlan(Base):
    __tablename__ = "content_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), index=True, nullable=True)
    platform: Mapped[str] = mapped_column(String(24), index=True)
    language_pref: Mapped[str] = mapped_column(String(32), default="english_urdu")
    planned_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="planned", index=True)
    theme: Mapped[str] = mapped_column(Text, default="")
    post_angle: Mapped[str] = mapped_column(Text, default="")
    image_prompt: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("generated_posts.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_note: Mapped[str] = mapped_column(Text, default="")


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("generated_posts.id"), index=True)
    platform: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
