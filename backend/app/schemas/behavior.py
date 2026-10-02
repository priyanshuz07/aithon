from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SessionStartRequest(ApiModel):
    session_id: UUID = Field(default_factory=uuid4)
    sdk_version: str = Field(default="1.0.0", min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9._-]+$")
    simulation_mode: Literal["normal_user", "bot_attack", "adaptive_bot"] | None = None

    @field_validator("session_id")
    @classmethod
    def validate_random_session_id(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("session_id must be a random UUID version 4")
        return value


class SessionStartResponse(ApiModel):
    session_id: UUID
    started_at: datetime
    last_seen_at: datetime
    created: bool


class BehaviorFeatures(ApiModel):
    page: str = Field(default="page", min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")
    click_count: int = Field(default=0, ge=0, le=1_000_000)
    page_visit_count: int = Field(default=0, ge=0, le=1_000_000)
    page_time_ms: int = Field(default=0, ge=0, le=86_400_000)
    average_inter_click_ms: int = Field(default=0, ge=0, le=86_400_000)
    form_submission_count: int = Field(default=0, ge=0, le=1_000_000)
    repeated_action_count: int = Field(default=0, ge=0, le=1_000_000)
    request_count: int = Field(default=0, ge=0, le=1_000_000)
    request_frequency_per_minute: float = Field(default=0, ge=0, le=1_000_000)
    session_duration_ms: int = Field(default=0, ge=0, le=604_800_000)
    pending_event_count: int = Field(default=0, ge=0, le=160)


class BehaviorEvent(ApiModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = Field(
        validation_alias=AliasChoices("type", "event_type"),
        min_length=1,
        max_length=80,
        pattern=r"^[a-zA-Z0-9_.-]+$",
    )
    occurred_at: datetime = Field(default_factory=utc_now, validation_alias=AliasChoices("at", "occurred_at"))
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("event_id must be a random UUID version 4")
        return value

    @field_validator("occurred_at")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    @model_validator(mode="after")
    def validate_privacy_safe_payload(self) -> "BehaviorEvent":
        expected_fields = {
            "interaction.click": {"action_id"},
            "interaction.form_submit": {"form_id"},
            "navigation.page_view": {"page"},
            "network.request": {"resource_type"},
            "session.start": {"sdk_session_id", "sdk_version"},
        }.get(self.event_type)
        if expected_fields is None or set(self.payload) != expected_fields:
            raise ValueError("event payload does not match an allowed privacy-safe event")

        for value in self.payload.values():
            if not isinstance(value, str) or len(value) > 80 or not value:
                raise ValueError("event payload values must be short identifiers")
            if not all(character.isalnum() or character in "_.-" for character in value):
                raise ValueError("event payload values must be safe identifiers")
        return self


class EventBatchRequest(ApiModel):
    session_id: UUID
    batch_id: UUID = Field(default_factory=uuid4)
    events: list[BehaviorEvent] = Field(min_length=1, max_length=50)
    features: BehaviorFeatures = Field(default_factory=BehaviorFeatures)

    @field_validator("session_id", "batch_id")
    @classmethod
    def validate_random_ids(cls, value: UUID) -> UUID:
        if value.version != 4:
            raise ValueError("IDs must be random UUID version 4 values")
        return value

    @model_validator(mode="after")
    def validate_session_start_event(self) -> "EventBatchRequest":
        for event in self.events:
            if event.event_type == "session.start" and event.payload["sdk_session_id"] != str(self.session_id):
                raise ValueError("session.start event must match the batch session_id")
        return self


class EventBatchResponse(ApiModel):
    session_id: UUID
    batch_id: UUID
    accepted_count: int
    duplicate_count: int
    total_event_count: int
    received_at: datetime


class SessionSummary(ApiModel):
    session_id: UUID
    started_at: datetime
    last_seen_at: datetime
    event_count: int
    event_type_counts: dict[str, int]
    latest_features: BehaviorFeatures | None = None


class RiskAnalysisResponse(ApiModel):
    session_id: UUID
    score: int = Field(ge=0, le=100)
    risk_level: str
    estimated_behavioral_category: str
    signals: list[dict[str, Any]]
    explanation: str
    recommended_response: str
    ml_prediction: dict[str, Any] | None = None
    behavioral_factors: dict[str, dict[str, Any]] = Field(default_factory=dict)


class BehaviorHealth(ApiModel):
    status: str
    database: str
