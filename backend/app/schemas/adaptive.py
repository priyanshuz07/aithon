from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.behavior import ApiModel


ResponseAction = Literal["allow", "challenge", "delay", "block"]


class AccessDecisionResponse(ApiModel):
    session_id: UUID
    request_id: UUID
    risk_score: int = Field(ge=0, le=100)
    risk_level: str
    estimated_behavioral_category: str
    ml_prediction: dict[str, object] | None = None
    signals: list[dict[str, object]]
    recommended_action: ResponseAction
    actual_response: ResponseAction
    reason: str
    delay_ms: int = Field(ge=0)
    safe_demo_mode: bool


class ChallengeIssueResponse(ApiModel):
    challenge_id: UUID
    question: str
    expires_at: datetime
    notice: str


class ChallengeAnswerRequest(ApiModel):
    answer: str = Field(min_length=1, max_length=3, pattern=r"^\d{1,3}$")


class ChallengeVerifyResponse(ApiModel):
    verified: bool
    actual_response: ResponseAction
    request_id: UUID
    reason: str


class AdminReviewRequest(ApiModel):
    actual_response: ResponseAction
    notes: str = Field(default="", max_length=1000)


class DecisionHistoryEntry(ApiModel):
    request_id: UUID
    recommended_action: ResponseAction
    actual_response: ResponseAction
    reason: str
    created_at: datetime
    decision_source: str
    reviewed_by: str | None = None
    review_notes: str = ""


class AdminReviewResponse(ApiModel):
    session_id: UUID
    decision: DecisionHistoryEntry


class BlockedDecisionResponse(ApiModel):
    request_id: UUID
    recommended_action: ResponseAction
    actual_response: ResponseAction
    reason: str
    created_at: datetime
