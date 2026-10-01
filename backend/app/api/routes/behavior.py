from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app.core.rate_limit import limit_event_batches, limit_session_starts
from app.core.config import get_settings
from app.core.decision_service import analyze_and_record
from app.db.session import get_db
from app.models import (
    EventDeduplication,
    SecurityEvent,
    Session,
    SessionIdentity,
)
from app.schemas.behavior import (
    BehaviorFeatures,
    BehaviorHealth,
    EventBatchRequest,
    EventBatchResponse,
    RiskAnalysisResponse,
    SessionStartRequest,
    SessionStartResponse,
    SessionSummary,
)

router = APIRouter(prefix="/api", tags=["behavior collection"])


def find_session(db: OrmSession, public_id: UUID) -> Session | None:
    identity = db.scalar(select(SessionIdentity).where(SessionIdentity.public_id == str(public_id)))
    if identity is not None:
        return db.get(Session, identity.session_id)

    return db.scalar(
        select(Session).where(
            Session.attributes["client_session_id"].as_string() == str(public_id)
        )
    )


def get_or_create_identity(db: OrmSession, session: Session, public_id: UUID) -> None:
    identity = db.scalar(select(SessionIdentity).where(SessionIdentity.session_id == session.id))
    if identity is None:
        db.add(SessionIdentity(session_id=session.id, public_id=str(public_id)))
        db.flush()


def session_start_response(session: Session, public_id: UUID, created: bool) -> SessionStartResponse:
    return SessionStartResponse(
        session_id=public_id,
        started_at=session.started_at,
        last_seen_at=session.last_seen_at,
        created=created,
    )


@router.post(
    "/session/start",
    response_model=SessionStartResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_session_starts)],
)
def start_session(
    payload: SessionStartRequest,
    response: Response,
    db: OrmSession = Depends(get_db),
) -> SessionStartResponse:
    public_id = payload.session_id
    existing = find_session(db, public_id)
    if existing is not None:
        try:
            get_or_create_identity(db, existing, public_id)
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = find_session(db, public_id)
            if existing is None:
                raise HTTPException(status_code=409, detail="Session ID is already in use")
        response.status_code = status.HTTP_200_OK
        return session_start_response(existing, public_id, created=False)

    session = Session(
        user_agent=None,
        attributes={"client_session_id": str(public_id), "sdk_version": payload.sdk_version},
    )
    db.add(session)
    try:
        db.flush()
        db.add(SessionIdentity(session_id=session.id, public_id=str(public_id)))
        db.commit()
        db.refresh(session)
    except IntegrityError:
        db.rollback()
        existing = find_session(db, public_id)
        if existing is None:
            raise HTTPException(status_code=409, detail="Session ID is already in use")
        response.status_code = status.HTTP_200_OK
        return session_start_response(existing, public_id, created=False)

    return session_start_response(session, public_id, created=True)


@router.post(
    "/events",
    response_model=EventBatchResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_event_batches)],
)
def ingest_events(
    payload: EventBatchRequest,
    response: Response,
    db: OrmSession = Depends(get_db),
) -> EventBatchResponse:
    session = find_session(db, payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    event_ids = list(dict.fromkeys(str(event.event_id) for event in payload.events))
    existing_ids = set(
        db.scalars(
            select(EventDeduplication.event_id).where(
                EventDeduplication.session_id == session.id,
                EventDeduplication.event_id.in_(event_ids),
            )
        ).all()
    )
    seen_ids: set[str] = set()
    accepted_count = 0
    duplicate_count = 0
    received_at = datetime.now(timezone.utc)

    try:
        for event in payload.events:
            event_id = str(event.event_id)
            if event_id in existing_ids or event_id in seen_ids:
                duplicate_count += 1
                continue

            seen_ids.add(event_id)
            db_event = SecurityEvent(
                session_id=session.id,
                event_type=event.event_type,
                payload={"event_id": event_id, "data": event.payload},
                occurred_at=event.occurred_at,
                received_at=received_at,
            )
            db.add(db_event)
            db.flush()
            db.add(EventDeduplication(session_id=session.id, event_id=event_id))
            accepted_count += 1

        attributes: dict[str, Any] = dict(session.attributes or {})
        attributes["latest_behavior_features"] = payload.features.model_dump()
        session.attributes = attributes
        session.last_seen_at = received_at
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        stored_ids = set(
            db.scalars(
                select(EventDeduplication.event_id).where(
                    EventDeduplication.session_id == session.id,
                    EventDeduplication.event_id.in_(event_ids),
                )
            ).all()
        )
        if len(stored_ids) == len(event_ids):
            total = db.scalar(
                select(func.count(SecurityEvent.id)).where(SecurityEvent.session_id == session.id)
            ) or 0
            response.status_code = status.HTTP_200_OK
            return EventBatchResponse(
                session_id=payload.session_id,
                batch_id=payload.batch_id,
                accepted_count=0,
                duplicate_count=len(payload.events),
                total_event_count=total,
                received_at=received_at,
            )
        raise HTTPException(status_code=409, detail="Event ID conflicts with an existing event") from exc

    total = db.scalar(
        select(func.count(SecurityEvent.id)).where(SecurityEvent.session_id == session.id)
    ) or 0
    if accepted_count == 0:
        response.status_code = status.HTTP_200_OK
    return EventBatchResponse(
        session_id=payload.session_id,
        batch_id=payload.batch_id,
        accepted_count=accepted_count,
        duplicate_count=duplicate_count,
        total_event_count=total,
        received_at=received_at,
    )


@router.get("/session/{session_id}", response_model=SessionSummary)
def get_session_summary(
    session_id: UUID,
    db: OrmSession = Depends(get_db),
) -> SessionSummary:
    session = find_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    event_count = db.scalar(
        select(func.count(SecurityEvent.id)).where(SecurityEvent.session_id == session.id)
    ) or 0
    rows = db.execute(
        select(SecurityEvent.event_type, func.count(SecurityEvent.id))
        .where(SecurityEvent.session_id == session.id)
        .group_by(SecurityEvent.event_type)
    ).all()
    raw_features = (session.attributes or {}).get("latest_behavior_features")
    try:
        features = BehaviorFeatures.model_validate(raw_features) if raw_features else None
    except ValidationError:
        features = None

    return SessionSummary(
        session_id=session_id,
        started_at=session.started_at,
        last_seen_at=session.last_seen_at,
        event_count=event_count,
        event_type_counts={event_type: count for event_type, count in rows},
        latest_features=features,
    )


@router.post("/session/{session_id}/analyze", response_model=RiskAnalysisResponse)
def analyze_session(
    session_id: UUID,
    db: OrmSession = Depends(get_db),
) -> RiskAnalysisResponse:
    session = find_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    analysis, _decision = analyze_and_record(db, session)

    return RiskAnalysisResponse(
        session_id=session_id,
        score=analysis.score,
        risk_level=analysis.risk_level,
        estimated_behavioral_category=analysis.estimated_behavioral_category,
        signals=analysis.signals,
        explanation=analysis.explanation,
        recommended_response=analysis.recommended_response,
        ml_prediction=analysis.ml_prediction,
    )


@router.get("/health", response_model=BehaviorHealth)
def behavior_health(db: OrmSession = Depends(get_db)) -> BehaviorHealth:
    try:
        db.execute(select(1))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return BehaviorHealth(status="ok", database="connected")
