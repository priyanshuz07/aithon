from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.behavior import ApiModel, BehaviorFeatures
from app.schemas.adaptive import DecisionHistoryEntry


class DashboardSession(ApiModel):
    session_id: str
    simulation_mode: str | None = None
    started_at: datetime
    last_seen_at: datetime
    click_count: int = 0
    request_frequency_per_minute: float = 0
    risk_score: int | None = None
    estimated_behavior_category: str
    risk_level: str
    response: str
    last_analysis_at: datetime | None = None


class DashboardTimePoint(ApiModel):
    time: str
    total: int
    normal: int
    suspicious: int


class DashboardRiskHistoryPoint(ApiModel):
    time: datetime
    session_id: str
    risk_score: int
    simulation_mode: str | None = None


class DashboardRecentEvent(ApiModel):
    time: datetime
    session_id: str
    event_type: str
    description: str
    simulation_mode: str | None = None


class DashboardTimelineEvent(ApiModel):
    time: datetime
    event_type: str
    description: str


class DashboardModelStatus(ApiModel):
    loaded: bool
    model_type: str
    training_dataset_type: str
    evaluation_metrics: dict[str, Any] | None = None
    last_training_status: str
    metrics_note: str | None = None


class DashboardSummary(ApiModel):
    total_sessions: int
    normal_sessions: int
    suspicious_sessions: int
    high_risk_sessions: int
    blocked_sessions: int
    active_sessions: int
    average_risk_score: int | None = None
    threats_detected: int = 0
    monitoring_status: str
    latest_activity_at: datetime | None = None
    risk_distribution: dict[str, int]
    response_distribution: dict[str, int]
    sessions_over_time: list[DashboardTimePoint]
    risk_history: list[DashboardRiskHistoryPoint] = Field(default_factory=list)
    recent_events: list[DashboardRecentEvent] = Field(default_factory=list)
    sessions: list[DashboardSession]
    model_status: DashboardModelStatus


class DashboardSessionDetails(ApiModel):
    session_id: str
    simulation_mode: str | None = None
    started_at: datetime
    last_seen_at: datetime
    last_analysis_at: datetime | None = None
    event_count: int
    event_type_counts: dict[str, int]
    behavior_timeline: list[DashboardTimelineEvent] = Field(default_factory=list)
    features: BehaviorFeatures | None = None
    risk_score: int | None = None
    risk_level: str
    estimated_behavior_category: str
    ml_prediction: dict[str, Any] | None = None
    behavioral_factors: dict[str, dict[str, Any]] = Field(default_factory=dict)
    rule_signals: list[dict[str, Any]]
    explanation: str
    recommended_action: str
    actual_response: str
    enforcement_status: str
    decision_history: list[DecisionHistoryEntry]