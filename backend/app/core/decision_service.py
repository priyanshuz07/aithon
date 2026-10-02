"""Server-owned risk evaluation and adaptive response audit operations."""

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from statistics import pstdev
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session as OrmSession

from app.core.config import get_settings
from app.core.risk_engine import RiskAnalysis, RiskEngineConfig, analyze_behavior
from app.ml.inference import default_artifact_path, load_model, predict_behavior
from app.models import (
    SecurityChallenge,
    SecurityDecision,
    SecurityEvent,
    Session,
    SessionIdentity,
    SessionRiskScore,
)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def latest_risk(db: OrmSession, session_id: int) -> SessionRiskScore | None:
    return db.scalar(
        select(SessionRiskScore)
        .where(SessionRiskScore.session_id == session_id)
        .order_by(desc(SessionRiskScore.created_at), desc(SessionRiskScore.id))
        .limit(1)
    )


def latest_decision(db: OrmSession, session_id: int) -> SecurityDecision | None:
    return db.scalar(
        select(SecurityDecision)
        .where(SecurityDecision.session_id == session_id)
        .order_by(desc(SecurityDecision.created_at), desc(SecurityDecision.id))
        .limit(1)
    )


def derive_behavior_features(db: OrmSession, session: Session) -> dict[str, Any]:
    events = db.scalars(
        select(SecurityEvent)
        .where(SecurityEvent.session_id == session.id)
        .order_by(SecurityEvent.occurred_at, SecurityEvent.id)
    ).all()

    click_actions: Counter[str] = Counter()
    submitted_forms: Counter[str] = Counter()
    visited_pages: Counter[str] = Counter()
    navigation_transitions: Counter[tuple[str, str]] = Counter()
    account_ids: set[str] = set()
    click_times: list[datetime] = []
    previous_page: str | None = None
    observed_clicks = observed_pages = observed_forms = observed_requests = 0
    for event in events:
        event_data = event.payload.get("data", event.payload)
        if not isinstance(event_data, dict):
            continue
        if event.event_type == "interaction.click":
            observed_clicks += 1
            click_times.append(_aware(event.occurred_at))
            action_id = event_data.get("action_id")
            if isinstance(action_id, str):
                click_actions[action_id] += 1
                account_ids.add(action_id)
        elif event.event_type == "interaction.form_submit":
            observed_forms += 1
            form_id = event_data.get("form_id")
            if isinstance(form_id, str):
                submitted_forms[form_id] += 1
                account_ids.add(form_id)
        elif event.event_type == "navigation.page_view":
            observed_pages += 1
            page_id = event_data.get("page")
            if isinstance(page_id, str):
                visited_pages[page_id] += 1
                if previous_page is not None:
                    navigation_transitions[(previous_page, page_id)] += 1
                previous_page = page_id
                account_ids.add(page_id)
        elif event.event_type == "network.request":
            observed_requests += 1

    repeated_actions = sum(count - 1 for count in click_actions.values() if count > 1)
    repeated_forms = sum(count - 1 for count in submitted_forms.values() if count > 1)
    repeated_pages = sum(count - 1 for count in visited_pages.values() if count > 1)
    repeated_navigation_transitions = sum(
        count - 1 for count in navigation_transitions.values() if count > 1
    )
    duration_ms = int(max(0.0, (_aware(session.last_seen_at) - _aware(session.started_at)).total_seconds()) * 1000)
    click_times.sort()
    click_intervals = [
        int((later - earlier).total_seconds() * 1000)
        for earlier, later in zip(click_times, click_times[1:])
    ]
    average_inter_click_ms = (
        round(sum(click_intervals) / len(click_intervals)) if click_intervals else 0
    )
    timing_variation_coefficient = (
        pstdev(click_intervals) / average_inter_click_ms
        if len(click_intervals) >= 4 and average_inter_click_ms > 0
        else None
    )
    request_count = observed_requests
    request_frequency = request_count * 60_000 / duration_ms if duration_ms >= 10_000 else 0
    account_related = any(
        any(token in identifier.lower() for token in ("account", "auth", "login", "signin"))
        and (click_actions[identifier] > 1 or submitted_forms[identifier] > 1)
        for identifier in account_ids
    )
    feature_values = {
        "click_count": observed_clicks,
        "page_visit_count": observed_pages,
        "average_inter_click_ms": average_inter_click_ms,
        "timing_interval_count": len(click_intervals),
        "timing_variation_coefficient": timing_variation_coefficient,
        "form_submission_count": observed_forms,
        "repeated_action_count": repeated_actions,
        "repeated_page_visit_count": repeated_pages,
        "repeated_navigation_transition_count": repeated_navigation_transitions,
        "repeated_form_submission_count": repeated_forms,
        "request_count": request_count,
        "request_frequency_per_minute": request_frequency,
        "session_duration_ms": duration_ms,
        "meaningful_event_count": observed_clicks + observed_pages + observed_forms,
        "account_related_repetition": account_related,
    }
    return feature_values


def analyze_and_record(db: OrmSession, session: Session) -> tuple[RiskAnalysis, SecurityDecision]:
    feature_values = derive_behavior_features(db, session)
    settings = get_settings()
    artifact_path = settings.ml_model_path or default_artifact_path()
    try:
        model_artifact = load_model(artifact_path)
    except ValueError:
        model_artifact = None
    ml_prediction = predict_behavior(feature_values, model_artifact)
    analysis = analyze_behavior(
        feature_values,
        RiskEngineConfig(
            medium_threshold=settings.risk_medium_threshold,
            high_threshold=settings.risk_high_threshold,
            critical_threshold=settings.risk_critical_threshold,
        ),
        ml_prediction=ml_prediction,
    )
    reason = analysis.explanation
    if settings.safe_demo_mode:
        reason += " Response is enforced only within the local demo interface."
    risk_record = SessionRiskScore(
        session_id=session.id,
        score=analysis.score,
        intent=analysis.estimated_behavioral_category,
        explanation={
            "risk_level": analysis.risk_level,
            "signals": analysis.signals,
            "explanation": analysis.explanation,
            "recommended_response": analysis.recommended_response,
            "ml_prediction": analysis.ml_prediction,
            "behavioral_factors": analysis.behavioral_factors,
        },
    )
    decision = SecurityDecision(
        session_id=session.id,
        action=analysis.recommended_response,
        recommended_action=analysis.recommended_response,
        decision_source="risk_engine",
        request_id=str(uuid4()),
        reason=reason,
    )
    db.add_all([risk_record, decision])
    db.commit()
    db.refresh(decision)
    return analysis, decision


def ensure_current_decision(
    db: OrmSession, session: Session
) -> tuple[SessionRiskScore, SecurityDecision]:
    risk = latest_risk(db, session.id)
    decision = latest_decision(db, session.id)
    stale = risk is None or _aware(session.last_seen_at) > _aware(risk.created_at)
    if stale or decision is None:
        analyze_and_record(db, session)
        risk = latest_risk(db, session.id)
        decision = latest_decision(db, session.id)
    if risk is None or decision is None:
        raise HTTPException(status_code=500, detail="Could not evaluate session policy")
    return risk, decision


def challenge_digest(challenge_id: str, answer: str) -> str:
    secret = get_settings().demo_challenge_secret.encode("utf-8")
    message = f"{challenge_id}:{answer}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def issue_demo_challenge(
    db: OrmSession, session: Session, decision: SecurityDecision
) -> tuple[SecurityChallenge, str]:
    if decision.action != "challenge":
        raise HTTPException(status_code=409, detail="A verification challenge is not required")
    first = 2 + secrets.randbelow(8)
    second = 2 + secrets.randbelow(8)
    challenge_id = str(uuid4())
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.demo_challenge_ttl_seconds)
    challenge = SecurityChallenge(
        id=challenge_id,
        session_id=session.id,
        decision_id=decision.id,
        answer_digest=challenge_digest(challenge_id, str(first + second)),
        expires_at=expires_at,
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)
    return challenge, f"What is {first} + {second}?"


def verify_demo_challenge(
    db: OrmSession, session: Session, challenge_id: str, answer: str
) -> SecurityDecision:
    challenge = db.get(SecurityChallenge, challenge_id)
    now = datetime.now(timezone.utc)
    if challenge is None or challenge.session_id != session.id:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if challenge.solved_at is not None or _aware(challenge.expires_at) <= now or challenge.attempts >= 5:
        raise HTTPException(status_code=410, detail="Challenge expired or already completed")

    original = db.get(SecurityDecision, challenge.decision_id)
    if original is None:
        raise HTTPException(status_code=410, detail="Challenge is no longer valid")
    if not hmac.compare_digest(challenge.answer_digest, challenge_digest(challenge_id, answer)):
        challenge.attempts += 1
        db.add(
            SecurityDecision(
                session_id=session.id,
                action="challenge",
                recommended_action=original.recommended_action,
                decision_source="challenge",
                reason=f"Demo verification answer was not accepted (attempt {challenge.attempts} of 5).",
            )
        )
        db.commit()
        raise HTTPException(status_code=422, detail="Verification answer was not accepted")

    challenge.solved_at = now
    decision = SecurityDecision(
        session_id=session.id,
        action="allow",
        recommended_action=original.recommended_action,
        decision_source="challenge",
        reason="Demo verification completed. Access allowed after the human challenge.",
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


def record_admin_review(
    db: OrmSession,
    session: Session,
    actual_response: str,
    notes: str,
    reviewer: str = "administrator",
) -> SecurityDecision:
    _risk, previous = ensure_current_decision(db, session)
    reason = f"Administrator review set the actual response to {actual_response}."
    decision = SecurityDecision(
        session_id=session.id,
        action=actual_response,
        recommended_action=previous.recommended_action,
        decision_source="admin_review",
        reviewed_by=reviewer,
        review_notes=notes.strip(),
        reason=reason,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision
