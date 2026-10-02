from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam
from sqlalchemy.orm import Session as OrmSession

from app.core.config import get_settings
from app.core.decision_service import analyze_and_record
from app.core.rate_limit import limit_demo_scenarios
from app.db.session import get_db
from app.models import EventDeduplication, SecurityEvent, Session, SessionIdentity
from app.schemas.demo import DemoScenario, DemoScenarioResponse

router = APIRouter(prefix="/api/demo", tags=["synthetic demo"])

_SCENARIOS = {
    "normal": {
        "title": "A / Normal browsing",
        "duration_ms": 120_000,
        "clicks": 4,
        "pages": 3,
        "forms": 1,
        "request_count": 12,
        "click_interval_ms": 20_000,
        "repeated_click": False,
        "repeated_form": False,
    },
    "automated": {
        "title": "B / Repetitive scraping-like behavior",
        "duration_ms": 120_000,
        "clicks": 2,
        "pages": 20,
        "forms": 0,
        "request_count": 150,
        "click_interval_ms": 15_000,
        "repeated_click": False,
        "repeated_form": False,
    },
    "high_frequency": {
        "title": "C / High-frequency automated browsing",
        "duration_ms": 60_000,
        "clicks": 20,
        "pages": 5,
        "forms": 0,
        "request_count": 80,
        "click_interval_ms": 100,
        "repeated_click": True,
        "repeated_form": False,
    },
    "critical": {
        "title": "D / Critical-risk simulated activity",
        "duration_ms": 60_000,
        "clicks": 60,
        "pages": 20,
        "forms": 8,
        "request_count": 120,
        "click_interval_ms": 100,
        "repeated_click": True,
        "repeated_form": True,
    },
}


@router.post(
    "/scenarios/{scenario}",
    response_model=DemoScenarioResponse,
    dependencies=[Depends(limit_demo_scenarios)],
)
def create_demo_scenario(
    scenario: DemoScenario = PathParam(),
    db: OrmSession = Depends(get_db),
) -> DemoScenarioResponse:
    settings = get_settings()
    if not settings.safe_demo_mode:
        raise HTTPException(status_code=503, detail="Synthetic scenarios are available only in safe demo mode")

    profile = _SCENARIOS[scenario]
    now = datetime.now(timezone.utc)
    started_at = now - timedelta(milliseconds=profile["duration_ms"])
    public_id = uuid4()
    session = Session(
        user_agent=None,
        started_at=started_at,
        last_seen_at=now,
        attributes={
            "client_session_id": str(public_id),
            "sdk_version": "synthetic-demo",
            "demo_scenario": scenario,
            "latest_behavior_features": {
                "page": "demo",
                "click_count": profile["clicks"],
                "page_visit_count": profile["pages"],
                "page_time_ms": profile["duration_ms"],
                "average_inter_click_ms": profile["click_interval_ms"],
                "form_submission_count": profile["forms"],
                "repeated_action_count": profile["clicks"] - 1 if profile["repeated_click"] else 0,
                "request_count": profile["request_count"],
                "request_frequency_per_minute": profile["request_count"] * 60_000 / profile["duration_ms"],
                "session_duration_ms": profile["duration_ms"],
                "pending_event_count": 0,
            },
        },
    )
    db.add(session)
    db.flush()
    db.add(SessionIdentity(session_id=session.id, public_id=str(public_id)))

    events: list[SecurityEvent] = []
    deduplications: list[EventDeduplication] = []
    for index in range(profile["clicks"]):
        event_id = str(uuid4())
        action_id = "demo.repeat" if profile["repeated_click"] else f"demo.action.{index}"
        received_at = started_at + timedelta(milliseconds=index * profile["click_interval_ms"])
        events.append(
            SecurityEvent(
                session_id=session.id,
                event_type="interaction.click",
                payload={"event_id": event_id, "data": {"action_id": action_id}},
                occurred_at=received_at,
                received_at=received_at,
            )
        )
        deduplications.append(EventDeduplication(session_id=session.id, event_id=event_id))

    for index in range(profile["pages"]):
        event_id = str(uuid4())
        received_at = started_at + timedelta(milliseconds=index * 500)
        events.append(
            SecurityEvent(
                session_id=session.id,
                event_type="navigation.page_view",
                payload={"event_id": event_id, "data": {"page": f"demo.page.{index}"}},
                occurred_at=received_at,
                received_at=received_at,
            )
        )
        deduplications.append(EventDeduplication(session_id=session.id, event_id=event_id))

    for index in range(profile["forms"]):
        event_id = str(uuid4())
        received_at = started_at + timedelta(milliseconds=index * 700)
        form_id = "demo.repeat.form" if profile["repeated_form"] else f"demo.form.{index}"
        events.append(
            SecurityEvent(
                session_id=session.id,
                event_type="interaction.form_submit",
                payload={"event_id": event_id, "data": {"form_id": form_id}},
                occurred_at=received_at,
                received_at=received_at,
            )
        )
        deduplications.append(EventDeduplication(session_id=session.id, event_id=event_id))

    for index in range(profile["request_count"]):
        event_id = str(uuid4())
        received_at = started_at + timedelta(milliseconds=index * 250)
        events.append(
            SecurityEvent(
                session_id=session.id,
                event_type="network.request",
                payload={"event_id": event_id, "data": {"resource_type": "fetch"}},
                occurred_at=received_at,
                received_at=received_at,
            )
        )
        deduplications.append(EventDeduplication(session_id=session.id, event_id=event_id))

    db.add_all(events)
    db.add_all(deduplications)
    db.commit()
    db.refresh(session)
    analysis, _decision = analyze_and_record(db, session)
    return DemoScenarioResponse(
        session_id=public_id,
        scenario=scenario,
        scenario_title=profile["title"],
        score=analysis.score,
        risk_level=analysis.risk_level,
        estimated_behavioral_category=analysis.estimated_behavioral_category,
        signals=analysis.signals,
        explanation=analysis.explanation,
        ml_prediction=analysis.ml_prediction,
        recommended_action=analysis.recommended_response,
        actual_response=analysis.recommended_response,
    )
