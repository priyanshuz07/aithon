from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.db.session import get_db
from app.models import SecurityEvent, Session
from app.models.security import utc_now
from app.schemas.security import EventCreate, EventRead, SessionCreate, SessionRead

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate,
    db: OrmSession = Depends(get_db),
) -> Session:
    session = Session(
        user_agent=payload.user_agent,
        attributes=payload.attributes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post(
    "/{session_id}/events",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
)
def record_event(
    session_id: int,
    payload: EventCreate,
    db: OrmSession = Depends(get_db),
) -> SecurityEvent:
    session = db.scalar(select(Session).where(Session.id == session_id))
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    event = SecurityEvent(
        session_id=session.id,
        event_type=payload.event_type,
        payload=payload.payload,
        occurred_at=utc_now(),
    )
    session.last_seen_at = event.occurred_at
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
