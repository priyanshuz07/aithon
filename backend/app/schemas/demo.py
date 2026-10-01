from typing import Any, Literal
from uuid import UUID

from app.schemas.adaptive import ResponseAction
from app.schemas.behavior import ApiModel


DemoScenario = Literal["normal", "automated", "high_frequency", "critical"]


class DemoScenarioResponse(ApiModel):
    session_id: UUID
    scenario: DemoScenario
    scenario_title: str
    score: int
    risk_level: str
    estimated_behavioral_category: str
    signals: list[dict[str, Any]]
    explanation: str
    ml_prediction: dict[str, Any] | None = None
    recommended_action: ResponseAction
    actual_response: ResponseAction
