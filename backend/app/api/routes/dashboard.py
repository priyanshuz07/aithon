from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session as OrmSession

from app.db.session import get_db
from app.core.config import get_settings
from app.models import SecurityDecision, SecurityEvent, Session, SessionIdentity, SessionRiskScore
from app.ml.inference import get_model_status
from app.schemas.behavior import BehaviorFeatures
from app.schemas.adaptive import DecisionHistoryEntry
from app.schemas.dashboard import (
    DashboardModelStatus,
    DashboardSession,
    DashboardSessionDetails,
    DashboardSummary,
    DashboardTimePoint,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_RISK_LEVELS = ("low", "medium", "high", "critical", "not_analyzed")
_RESPONSES = ("allow", "challenge", "delay", "block", "not_analyzed")


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _session_ids(db: OrmSession, sessions: list[Session]) -> dict[int, str]:
    identities = db.scalars(
        select(SessionIdentity).where(SessionIdentity.session_id.in_([item.id for item in sessions]))
    ).all() if sessions else []
    public_ids = {identity.session_id: identity.public_id for identity in identities}
    return {item.id: public_ids.get(item.id, f"legacy-{item.id}") for item in sessions}


def _latest_records(db: OrmSession, model: type[Any]) -> dict[int, Any]:
    ranked = (
        select(
            model.id.label("record_id"),
            model.session_id.label("session_id"),
            func.row_number()
            .over(partition_by=model.session_id, order_by=(desc(model.created_at), desc(model.id)))
            .label("row_number"),
        )
        .subquery()
    )
    record_ids = db.scalars(select(ranked.c.record_id).where(ranked.c.row_number == 1)).all()
    records = db.scalars(select(model).where(model.id.in_(record_ids))).all() if record_ids else []
    return {record.session_id: record for record in records}


def _features(session: Session) -> BehaviorFeatures | None:
    raw = (session.attributes or {}).get("latest_behavior_features")
    try:
        return BehaviorFeatures.model_validate(raw) if raw else None
    except ValidationError:
        return None


def _risk_level(score: int | None, risk: SessionRiskScore | None) -> str:
    if risk is None or score is None:
        return "not_analyzed"
    stored_level = (risk.explanation or {}).get("risk_level")
    if stored_level in _RISK_LEVELS:
        return stored_level
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _category(risk: SessionRiskScore | None) -> str:
    return risk.intent if risk and risk.intent else "unknown_or_insufficient_evidence"


def _as_dashboard_session(
    session: Session,
    public_id: str,
    risk: SessionRiskScore | None,
    decision: SecurityDecision | None,
) -> DashboardSession:
    features = _features(session)
    score = risk.score if risk else None
    return DashboardSession(
        session_id=public_id,
        started_at=_aware(session.started_at),
        last_seen_at=_aware(session.last_seen_at),
        click_count=features.click_count if features else 0,
        request_frequency_per_minute=features.request_frequency_per_minute if features else 0,
        risk_score=score,
        estimated_behavior_category=_category(risk),
        risk_level=_risk_level(score, risk),
        response=decision.action if decision else "not_analyzed",
        last_analysis_at=_aware(risk.created_at) if risk else None,
    )


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    limit: int = Query(default=250, ge=1, le=500),
    db: OrmSession = Depends(get_db),
) -> DashboardSummary:
    now = datetime.now(timezone.utc)
    sessions = db.scalars(select(Session).order_by(desc(Session.started_at))).all()
    identities = _session_ids(db, sessions)
    risks = _latest_records(db, SessionRiskScore)
    decisions = _latest_records(db, SecurityDecision)

    risk_distribution = Counter({level: 0 for level in _RISK_LEVELS})
    response_distribution = Counter({action: 0 for action in _RESPONSES})
    normal_sessions = suspicious_sessions = high_risk_sessions = blocked_sessions = 0
    active_sessions = 0
    latest_activity: datetime | None = None
    for session in sessions:
        risk = risks.get(session.id)
        decision = decisions.get(session.id)
        level = _risk_level(risk.score if risk else None, risk)
        response = decision.action if decision else "not_analyzed"
        risk_distribution[level] += 1
        response_distribution[response] += 1
        normal_sessions += _category(risk) == "normal_browsing"
        suspicious_sessions += level in ("medium", "high", "critical")
        high_risk_sessions += level in ("high", "critical")
        blocked_sessions += response == "block"
        last_seen = _aware(session.last_seen_at)
        active_sessions += last_seen >= now - timedelta(minutes=5)
        if latest_activity is None or last_seen > latest_activity:
            latest_activity = last_seen

    time_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    hourly: dict[datetime, list[int]] = {}
    for index in range(24):
        hourly[time_start + timedelta(hours=index)] = [0, 0, 0]
    for session in sessions:
        started = _aware(session.started_at)
        bucket = started.replace(minute=0, second=0, microsecond=0)
        if bucket not in hourly:
            continue
        counts = hourly[bucket]
        counts[0] += 1
        level = _risk_level(
            risks[session.id].score if session.id in risks else None,
            risks.get(session.id),
        )
        if _category(risks.get(session.id)) == "normal_browsing":
            counts[1] += 1
        elif level in ("medium", "high", "critical"):
            counts[2] += 1

    recent_sessions = sessions[:limit]
    dashboard_sessions = [
        _as_dashboard_session(
            session,
            identities[session.id],
            risks.get(session.id),
            decisions.get(session.id),
        )
        for session in recent_sessions
    ]
    db.execute(select(1))
    return DashboardSummary(
        total_sessions=len(sessions),
        normal_sessions=normal_sessions,
        suspicious_sessions=suspicious_sessions,
        high_risk_sessions=high_risk_sessions,
        blocked_sessions=blocked_sessions,
        active_sessions=active_sessions,
        monitoring_status="online",
        latest_activity_at=latest_activity,
        risk_distribution=dict(risk_distribution),
        response_distribution=dict(response_distribution),
        sessions_over_time=[
            DashboardTimePoint(
                time=bucket.isoformat(), total=counts[0], normal=counts[1], suspicious=counts[2]
            )
            for bucket, counts in hourly.items()
        ],
        sessions=dashboard_sessions,
        model_status=DashboardModelStatus(**get_model_status(get_settings().ml_model_path)),
    )


@router.get("/sessions/{session_id}", response_model=DashboardSessionDetails)
def dashboard_session_details(
    session_id: str,
    db: OrmSession = Depends(get_db),
) -> DashboardSessionDetails:
    if session_id.startswith("legacy-"):
        try:
            session = db.get(Session, int(session_id.removeprefix("legacy-")))
        except ValueError:
            session = None
    else:
        try:
            public_id = str(UUID(session_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc
        identity = db.scalar(select(SessionIdentity).where(SessionIdentity.public_id == public_id))
        session = db.get(Session, identity.session_id) if identity else None
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    identity = db.scalar(select(SessionIdentity).where(SessionIdentity.session_id == session.id))
    public_id = identity.public_id if identity else f"legacy-{session.id}"
    risk = db.scalar(
        select(SessionRiskScore)
        .where(SessionRiskScore.session_id == session.id)
        .order_by(desc(SessionRiskScore.created_at), desc(SessionRiskScore.id))
        .limit(1)
    )
    decision = db.scalar(
        select(SecurityDecision)
        .where(SecurityDecision.session_id == session.id)
        .order_by(desc(SecurityDecision.created_at), desc(SecurityDecision.id))
        .limit(1)
    )
    history = db.scalars(
        select(SecurityDecision)
        .where(SecurityDecision.session_id == session.id)
        .order_by(desc(SecurityDecision.created_at), desc(SecurityDecision.id))
        .limit(25)
    ).all()
    event_rows = db.execute(
        select(SecurityEvent.event_type, func.count(SecurityEvent.id))
        .where(SecurityEvent.session_id == session.id)
        .group_by(SecurityEvent.event_type)
    ).all()
    event_counts = {event_type: count for event_type, count in event_rows}
    explanation_data: dict[str, Any] = risk.explanation or {} if risk else {}
    action = decision.action if decision else "not_analyzed"
    features = _features(session)
    return DashboardSessionDetails(
        session_id=public_id,
        started_at=_aware(session.started_at),
        last_seen_at=_aware(session.last_seen_at),
        last_analysis_at=_aware(risk.created_at) if risk else None,
        event_count=sum(event_counts.values()),
        event_type_counts=event_counts,
        features=features,
        risk_score=risk.score if risk else None,
        risk_level=_risk_level(risk.score if risk else None, risk),
        estimated_behavior_category=_category(risk),
        ml_prediction=explanation_data.get("ml_prediction"),
        rule_signals=explanation_data.get("signals", []),
        explanation=explanation_data.get("explanation", "No rule-based analysis has been recorded."),
        recommended_action=decision.recommended_action if decision else explanation_data.get("recommended_response", action),
        actual_response=action,
        enforcement_status=(
            "Safe demo UI gate; API and dashboard remain available"
            if get_settings().safe_demo_mode
            else "Demo response policy is active; no network-level firewall is configured"
        ),
        decision_history=[
            DecisionHistoryEntry(
                request_id=UUID(item.request_id),
                recommended_action=item.recommended_action,
                actual_response=item.action,
                reason=item.reason,
                created_at=_aware(item.created_at),
                decision_source=item.decision_source,
                reviewed_by=item.reviewed_by,
                review_notes="",
            )
            for item in history
        ],
    )