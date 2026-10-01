import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.dashboard import router
from app.db.base import Base
from app.db.session import get_db
from app.models import SecurityDecision, SecurityEvent, Session, SessionIdentity, SessionRiskScore


class DashboardApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.app = FastAPI()
        self.app.include_router(router)

        def override_get_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)
        self.public_id = str(uuid4())
        now = datetime.now(timezone.utc)
        with self.session_factory() as db:
            session = Session(
                attributes={
                    "client_session_id": self.public_id,
                    "latest_behavior_features": {
                        "page": "products",
                        "click_count": 7,
                        "page_visit_count": 3,
                        "request_count": 12,
                        "request_frequency_per_minute": 6,
                        "session_duration_ms": 120_000,
                    },
                },
                started_at=now,
                last_seen_at=now,
            )
            db.add(session)
            db.flush()
            db.add(SessionIdentity(session_id=session.id, public_id=self.public_id))
            db.add(
                SecurityEvent(
                    session_id=session.id,
                    event_type="interaction.click",
                    payload={"data": {"action_id": "cart.add"}},
                    occurred_at=now,
                )
            )
            db.add(
                SessionRiskScore(
                    session_id=session.id,
                    score=0,
                    intent="normal_browsing",
                    explanation={
                        "risk_level": "low",
                        "signals": [],
                        "explanation": "No risk rules triggered.",
                        "recommended_response": "allow",
                    },
                    created_at=now,
                )
            )
            db.add(SecurityDecision(session_id=session.id, action="allow", reason="No risk rules triggered."))
            db.commit()

    def tearDown(self) -> None:
        self.client.close()
        self.engine.dispose()

    def test_summary_and_details_reflect_persisted_records(self) -> None:
        summary_response = self.client.get("/api/dashboard/summary?limit=10")
        self.assertEqual(summary_response.status_code, 200)
        summary = summary_response.json()
        self.assertEqual(summary["total_sessions"], 1)
        self.assertEqual(summary["normal_sessions"], 1)
        self.assertEqual(summary["risk_distribution"]["low"], 1)
        self.assertEqual(summary["response_distribution"]["allow"], 1)
        row = summary["sessions"][0]
        self.assertEqual(row["session_id"], self.public_id)
        self.assertEqual(row["click_count"], 7)
        self.assertEqual(row["risk_score"], 0)
        self.assertEqual(row["response"], "allow")

        details_response = self.client.get(f"/api/dashboard/sessions/{self.public_id}")
        self.assertEqual(details_response.status_code, 200)
        details = details_response.json()
        self.assertEqual(details["event_count"], 1)
        self.assertEqual(details["features"]["click_count"], 7)
        self.assertEqual(details["risk_score"], 0)
        self.assertEqual(details["actual_response"], "allow")
        self.assertEqual(details["rule_signals"], [])
        self.assertIsNone(details["ml_prediction"])


if __name__ == "__main__":
    unittest.main()