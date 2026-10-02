from datetime import timezone
from uuid import UUID
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings, get_settings
from app.core.decision_service import (
    ensure_current_decision,
    issue_demo_challenge,
    record_admin_review,
    verify_demo_challenge,
)
from app.db.session import get_db
from app.models import SecurityDecision, Session, SessionIdentity
from app.schemas.adaptive import (
    AccessDecisionResponse,
    AdminReviewRequest,
    AdminReviewResponse,
    BlockedDecisionResponse,
    ChallengeAnswerRequest,
    ChallengeIssueResponse,
    ChallengeVerifyResponse,
    DecisionHistoryEntry,
)

router = APIRouter(prefix="/api", tags=["adaptive response"])


def _find_session(db: OrmSession, session_id: UUID) -> Session | None:
    identity = db.scalar(select(SessionIdentity).where(SessionIdentity.public_id == str(session_id)))
    if identity is not None:
        return db.get(Session, identity.session_id)
    return db.scalar(
        select(Session).where(Session.attributes["client_session_id"].as_string() == str(session_id))
    )


def _public_id(db: OrmSession, session: Session) -> UUID:
    identity = db.scalar(select(SessionIdentity).where(SessionIdentity.session_id == session.id))
    if identity is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return UUID(identity.public_id)


def _history_entry(decision: SecurityDecision) -> DecisionHistoryEntry:
    created_at = decision.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return DecisionHistoryEntry(
        request_id=UUID(decision.request_id),
        recommended_action=decision.recommended_action,
        actual_response=decision.action,
        reason=decision.reason,
        created_at=created_at,
        decision_source=decision.decision_source,
        reviewed_by=decision.reviewed_by,
        review_notes=decision.review_notes,
    )


def require_admin(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="Administrative review is not configured")
    scheme, separator, token = (authorization or "").partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.isascii()
        or not secrets.compare_digest(token.encode("ascii"), settings.admin_api_key.encode("utf-8"))
    ):
        raise HTTPException(status_code=401, detail="Administrative authentication required")
    return "administrator"


@router.get("/session/{session_id}/access", response_model=AccessDecisionResponse)
def check_session_access(
    session_id: UUID,
    db: OrmSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AccessDecisionResponse:
    session = _find_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    risk, decision = ensure_current_decision(db, session)
    level = (risk.explanation or {}).get("risk_level", "unknown")
    return AccessDecisionResponse(
        session_id=session_id,
        request_id=UUID(decision.request_id),
        risk_score=risk.score,
        risk_level=level,
        estimated_behavioral_category=risk.intent or "unknown_or_insufficient_evidence",
        ml_prediction=(risk.explanation or {}).get("ml_prediction"),
        signals=(risk.explanation or {}).get("signals", []),
        behavioral_factors=(risk.explanation or {}).get("behavioral_factors", {}),
        recommended_action=decision.recommended_action,
        actual_response=decision.action,
        reason=decision.reason,
        delay_ms=settings.adaptive_delay_ms if decision.action == "delay" else 0,
        safe_demo_mode=settings.safe_demo_mode,
    )


@router.post("/session/{session_id}/challenge", response_model=ChallengeIssueResponse)
def create_challenge(
    session_id: UUID,
    db: OrmSession = Depends(get_db),
) -> ChallengeIssueResponse:
    session = _find_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    _risk, decision = ensure_current_decision(db, session)
    challenge, question = issue_demo_challenge(db, session, decision)
    expires_at = challenge.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return ChallengeIssueResponse(
        challenge_id=UUID(challenge.id),
        question=question,
        expires_at=expires_at,
        notice="Demo human-verification challenge only. This is not a production CAPTCHA.",
    )


@router.post(
    "/session/{session_id}/challenge/{challenge_id}/verify",
    response_model=ChallengeVerifyResponse,
)
def complete_challenge(
    session_id: UUID,
    challenge_id: UUID,
    payload: ChallengeAnswerRequest,
    db: OrmSession = Depends(get_db),
) -> ChallengeVerifyResponse:
    session = _find_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    decision = verify_demo_challenge(db, session, str(challenge_id), payload.answer)
    return ChallengeVerifyResponse(
        verified=True,
        actual_response=decision.action,
        request_id=UUID(decision.request_id),
        reason=decision.reason,
    )


@router.get("/decision/{request_id}", response_model=BlockedDecisionResponse)
def get_blocked_decision(
    request_id: UUID,
    db: OrmSession = Depends(get_db),
) -> BlockedDecisionResponse:
    decision = db.scalar(select(SecurityDecision).where(SecurityDecision.request_id == str(request_id)))
    if decision is None or decision.action != "block":
        raise HTTPException(status_code=404, detail="Blocked request not found")
    created_at = decision.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return BlockedDecisionResponse(
        request_id=request_id,
        recommended_action=decision.recommended_action,
        actual_response=decision.action,
        reason=decision.reason,
        created_at=created_at,
    )


@router.post(
    "/admin/sessions/{session_id}/review",
    response_model=AdminReviewResponse,
    dependencies=[Depends(require_admin)],
)
def review_session(
    session_id: UUID,
    payload: AdminReviewRequest,
    db: OrmSession = Depends(get_db),
) -> AdminReviewResponse:
    session = _find_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    decision = record_admin_review(
        db,
        session,
        payload.actual_response,
        payload.notes,
    )
    return AdminReviewResponse(session_id=session_id, decision=_history_entry(decision))


def session_decision_history(db: OrmSession, session_id: int) -> list[DecisionHistoryEntry]:
    decisions = db.scalars(
        select(SecurityDecision)
        .where(SecurityDecision.session_id == session_id)
        .order_by(desc(SecurityDecision.created_at), desc(SecurityDecision.id))
        .limit(25)
    ).all()
    return [_history_entry(decision) for decision in decisions]
