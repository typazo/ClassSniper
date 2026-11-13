"""Pydantic request and response schemas for ClassSniper API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.services.cs_requirements import normalize_completed_courses, normalize_course_code
from app.services.notifiers import is_valid_discord_user_id, is_valid_discord_webhook_url


class BootstrapRequest(BaseModel):
    username: str = Field(min_length=2, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RegisterInviteRequest(BaseModel):
    invite_code: str = Field(min_length=4, max_length=64)
    username: str = Field(min_length=2, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class CreateWatchRequest(BaseModel):
    roster: str = Field(min_length=3, max_length=10)
    subject: str = Field(min_length=1, max_length=12)
    catalog_nbr: str = Field(min_length=1, max_length=12)
    class_nbr: Optional[int] = Field(default=None, ge=1, le=999999)
    enroll_group_idx: Optional[int] = Field(default=None, ge=0, le=100)
    component_filter: Optional[str] = Field(default=None, max_length=10)
    mode: Literal["exact", "linked_group", "any_section"] = "exact"
    trigger_on: Literal["open", "open_or_waitlist"] = "open"
    priority: int = Field(default=1, ge=1, le=2)
    auto_pause: bool = False
    ithaca_or_virtual: bool = False
    cooldown_sec: int = Field(default=60, ge=0, le=86400)


class UpdateWatchRequest(BaseModel):
    active: Optional[bool] = None
    auto_pause: Optional[bool] = None
    trigger_on: Optional[Literal["open", "open_or_waitlist"]] = None
    priority: Optional[int] = Field(default=None, ge=1, le=2)
    cooldown_sec: Optional[int] = Field(default=None, ge=0, le=86400)


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=512)
    auth: str = Field(min_length=8, max_length=256)


class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2048)
    keys: PushSubscriptionKeys
    device_label: str = Field(default="Browser", min_length=1, max_length=80)


class PushUnsubscribeRequest(BaseModel):
    endpoint: Optional[str] = None
    id: Optional[int] = None


class NotificationPreferencesRequest(BaseModel):
    discord_user_id: Optional[str] = None
    discord_ping_enabled: Optional[bool] = None
    web_push_enabled: Optional[bool] = None
    personal_webhook_url: Optional[str] = None

    @field_validator("discord_user_id")
    @classmethod
    def check_discord_uid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if cleaned == "":
            return ""
        if not is_valid_discord_user_id(cleaned):
            raise ValueError("Discord User ID must be 15-22 digits (copy from Discord Developer Mode)")
        return cleaned

    @field_validator("personal_webhook_url")
    @classmethod
    def check_personal_webhook(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if cleaned == "":
            return ""
        if not is_valid_discord_webhook_url(cleaned):
            raise ValueError("Webhook URL must start with https://discord.com/api/webhooks/...")
        return cleaned


class TestNotifyRequest(BaseModel):
    target: Literal["all", "web_push", "discord"] = "all"


class CreateInviteRequest(BaseModel):
    max_uses: int = Field(default=1, ge=1, le=50)
    expires_hours: Optional[int] = Field(default=72, ge=1, le=24 * 90)
    note: str = Field(default="", max_length=100)


class UpdateAdminSettingsRequest(BaseModel):
    discord_shared_webhook_url: Optional[str] = None
    poll_max_rps: Optional[float] = Field(default=None, ge=0.2, le=3.0)

    @field_validator("discord_shared_webhook_url")
    @classmethod
    def check_shared_webhook(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if cleaned == "":
            return ""
        if not is_valid_discord_webhook_url(cleaned):
            raise ValueError("Shared Discord Webhook URL must start with https://discord.com/api/webhooks/...")
        return cleaned


class SyncCatalogRequest(BaseModel):
    roster: Optional[str] = None
    subject: Optional[str] = None


class RefreshSubjectsRequest(BaseModel):
    roster: str = Field(min_length=3, max_length=10)
    subjects: list[str] = Field(min_length=1, max_length=20)


class CompletedPrereqsRequest(BaseModel):
    completed_courses: list[str] = Field(default_factory=list, max_length=200)
    include_implied_prereqs: Optional[bool] = None

    @field_validator("completed_courses")
    @classmethod
    def check_completed_courses(cls, v: list[str]) -> list[str]:
        cleaned = [raw.strip() for raw in v if raw and raw.strip()]
        invalid = [raw for raw in cleaned if normalize_course_code(raw) is None]
        if invalid:
            raise ValueError(f"Invalid course code(s): {', '.join(invalid[:5])}")
        return normalize_completed_courses(cleaned)


class UserPreferencesRequest(BaseModel):
    major_mode: Optional[Literal["none", "cs", "ilr"]] = None
    show_cs_features: Optional[bool] = None


class CreateScheduleRequest(BaseModel):
    roster: str = Field(min_length=3, max_length=10)
    name: str = Field(min_length=1, max_length=80)
    duplicate_from_id: Optional[int] = Field(default=None, ge=1)


class UpdateScheduleRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    is_active: Optional[bool] = None
    share_enabled: Optional[bool] = None
    regenerate_share_token: Optional[bool] = None


class AddScheduleCourseRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=12)
    catalog_nbr: str = Field(min_length=1, max_length=12)
    enabled: bool = True
    selected_units: Optional[float] = Field(default=None, ge=0.0, le=20.0)
    selected_class_nbrs: Optional[list[int]] = Field(default=None, max_length=20)
    locked_class_nbrs: Optional[list[int]] = Field(default=None, max_length=20)
    color_idx: Optional[int] = Field(default=None, ge=0, le=24)


class QuickAddScheduleCourseRequest(AddScheduleCourseRequest):
    roster: str = Field(min_length=3, max_length=10)


class UpdateScheduleCourseRequest(BaseModel):
    enabled: Optional[bool] = None
    selected_units: Optional[float] = Field(default=None, ge=0.0, le=20.0)
    selected_class_nbrs: Optional[list[int]] = Field(default=None, max_length=20)
    locked_class_nbrs: Optional[list[int]] = Field(default=None, max_length=20)
    color_idx: Optional[int] = Field(default=None, ge=0, le=24)


class ApplyGeneratedItem(BaseModel):
    item_id: int = Field(ge=1)
    selected_class_nbrs: list[int] = Field(default_factory=list, max_length=20)


class ApplyGeneratedScheduleRequest(BaseModel):
    items: list[ApplyGeneratedItem] = Field(min_length=1, max_length=30)


class CreateScheduleBlockRequest(BaseModel):
    label: str = Field(default="Busy", min_length=1, max_length=60)
    days: list[Literal["M", "T", "W", "R", "F", "Sa", "Su"]] = Field(min_length=1, max_length=7)
    start_min: int = Field(ge=0, le=1439)
    end_min: int = Field(ge=1, le=1440)
    enabled: bool = True


class UpdateScheduleBlockRequest(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=60)
    days: Optional[list[Literal["M", "T", "W", "R", "F", "Sa", "Su"]]] = Field(default=None, min_length=1, max_length=7)
    start_min: Optional[int] = Field(default=None, ge=0, le=1439)
    end_min: Optional[int] = Field(default=None, ge=1, le=1440)
    enabled: Optional[bool] = None
