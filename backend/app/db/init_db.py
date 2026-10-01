from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, func, inspect, select, text

from app.db.base import Base
from app.db.session import engine
from app.models import (
    EventDeduplication,
    SecurityDecision,
    SecurityChallenge,
    SecurityEvent,
    Session,
    SessionIdentity,
    SessionRiskScore,
)


def migrate_security_decision_schema(bind=engine) -> None:
    inspector = inspect(bind)
    if "security_decisions" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("security_decisions")}
    add_recommendation = "recommended_action" not in existing_columns
    additions = {
        "recommended_action": "VARCHAR(16) NOT NULL DEFAULT 'allow'",
        "request_id": "VARCHAR(36)",
        "decision_source": "VARCHAR(20) NOT NULL DEFAULT 'risk_engine'",
        "reviewed_by": "VARCHAR(80)",
        "review_notes": "TEXT NOT NULL DEFAULT ''",
    }
    with bind.begin() as connection:
        for name, declaration in additions.items():
            if name not in existing_columns:
                connection.execute(text(f"ALTER TABLE security_decisions ADD COLUMN {name} {declaration}"))
        if add_recommendation:
            connection.execute(text("UPDATE security_decisions SET recommended_action = action"))
        missing_ids = connection.execute(
            text("SELECT id FROM security_decisions WHERE request_id IS NULL")
        ).scalars().all()
        for decision_id in missing_ids:
            connection.execute(
                text("UPDATE security_decisions SET request_id = :request_id WHERE id = :id"),
                {"request_id": str(uuid4()), "id": decision_id},
            )


def migrate_security_event_schema(bind=engine) -> None:
    inspector = inspect(bind)
    if "events" not in inspector.get_table_names():
        return
    existing_columns = {column["name"] for column in inspector.get_columns("events")}
    if "received_at" in existing_columns:
        return
    with bind.begin() as connection:
        connection.execute(text("ALTER TABLE events ADD COLUMN received_at DATETIME"))
        connection.execute(text("UPDATE events SET received_at = occurred_at WHERE received_at IS NULL"))


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_security_decision_schema()
    migrate_security_event_schema()


def purge_expired_sessions(bind=engine, retention_days: int = 90) -> int:
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    expired_ids = select(Session.id).where(Session.last_seen_at < cutoff)
    with bind.begin() as connection:
        expired_count = connection.scalar(select(func.count()).select_from(Session).where(Session.id.in_(expired_ids))) or 0
        if not expired_count:
            return 0
        dependent_tables = (
            SecurityChallenge.__table__,
            SecurityDecision.__table__,
            SessionRiskScore.__table__,
            EventDeduplication.__table__,
            SecurityEvent.__table__,
            SessionIdentity.__table__,
        )
        for table in dependent_tables:
            connection.execute(delete(table).where(table.c.session_id.in_(expired_ids)))
        connection.execute(delete(Session.__table__).where(Session.id.in_(expired_ids)))
    return int(expired_count)


__all__ = ["initialize_database"]
