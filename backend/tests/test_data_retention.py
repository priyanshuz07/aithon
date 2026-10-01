import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.init_db import purge_expired_sessions
from app.models import (
    EventDeduplication,
    SecurityChallenge,
    SecurityDecision,
    SecurityEvent,
    Session,
    SessionIdentity,
    SessionRiskScore,
)


class DataRetentionTests(unittest.TestCase):
    def test_purge_removes_all_expired_session_rows_only(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=engine)
        factory = sessionmaker(bind=engine)
        now = datetime.now(timezone.utc)
        expired_id = str(uuid4())
        active_id = str(uuid4())
        try:
            with factory() as db:
                expired = Session(
                    attributes={"client_session_id": expired_id},
                    started_at=now - timedelta(days=120),
                    last_seen_at=now - timedelta(days=120),
                )
                active = Session(
                    attributes={"client_session_id": active_id},
                    started_at=now,
                    last_seen_at=now,
                )
                db.add_all([expired, active])
                db.flush()
                db.add_all(
                    [
                        SessionIdentity(session_id=expired.id, public_id=expired_id),
                        SessionIdentity(session_id=active.id, public_id=active_id),
                    ]
                )
                event = SecurityEvent(
                    session_id=expired.id,
                    event_type="interaction.click",
                    payload={"data": {"action_id": "button.demo"}},
                    occurred_at=now - timedelta(days=120),
                    received_at=now - timedelta(days=120),
                )
                db.add(event)
                db.add(SessionRiskScore(session_id=expired.id, score=10, intent="normal_browsing", explanation={}))
                decision = SecurityDecision(session_id=expired.id, action="allow", reason="expired test row")
                db.add(decision)
                db.flush()
                db.add(EventDeduplication(session_id=expired.id, event_id=str(uuid4())))
                db.add(
                    SecurityChallenge(
                        id=str(uuid4()),
                        session_id=expired.id,
                        decision_id=decision.id,
                        answer_digest="0" * 64,
                        expires_at=now,
                    )
                )
                expired_pk = expired.id
                active_pk = active.id
                db.commit()

            self.assertEqual(purge_expired_sessions(engine, retention_days=90), 1)
            with factory() as db:
                self.assertIsNone(db.get(Session, expired_pk))
                self.assertIsNotNone(db.get(Session, active_pk))
                self.assertEqual(db.query(SecurityEvent).filter_by(session_id=expired_pk).count(), 0)
                self.assertEqual(db.query(SessionRiskScore).filter_by(session_id=expired_pk).count(), 0)
                self.assertEqual(db.query(SecurityDecision).filter_by(session_id=expired_pk).count(), 0)
                self.assertEqual(db.query(SecurityChallenge).filter_by(session_id=expired_pk).count(), 0)
                self.assertEqual(db.query(EventDeduplication).filter_by(session_id=expired_pk).count(), 0)
                self.assertEqual(db.query(SessionIdentity).filter_by(session_id=expired_pk).count(), 0)
        finally:
            engine.dispose()

    def test_retention_rejects_invalid_window(self) -> None:
        engine = create_engine("sqlite://")
        try:
            with self.assertRaises(ValueError):
                purge_expired_sessions(engine, retention_days=0)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
