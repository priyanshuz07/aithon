import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.adaptive import router as adaptive_router
from app.api.routes.dashboard import router as dashboard_router
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.models import SecurityDecision, SecurityEvent, Session, SessionIdentity
from app.ml.inference import train_model


class AdaptiveResponseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.settings = Settings(
            safe_demo_mode=True,
            adaptive_delay_ms=37,
            ml_model_path="missing-test-model.joblib",
            demo_challenge_secret="unit-test-challenge-signing-secret-123456",
            admin_api_key="unit-test-administrator-key-123456789",
        )
        self.app = FastAPI()
        self.app.include_router(adaptive_router)
        self.app.include_router(dashboard_router)

        def override_get_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()

        self.app.dependency_overrides[get_db] = override_get_db
        self.app.dependency_overrides[get_settings] = lambda: self.settings
        self.settings_patch = patch("app.core.decision_service.get_settings", return_value=self.settings)
        self.settings_patch.start()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.client.close()
        self.settings_patch.stop()
        self.engine.dispose()

    def create_session(self, profile: dict, include_events: bool = True) -> str:
        public_id = str(uuid4())
        duration = profile.get("session_duration_ms", 60_000)
        now = datetime.now(timezone.utc)
        started_at = now - timedelta(milliseconds=duration)
        attributes = {
            "client_session_id": public_id,
            "latest_behavior_features": {
                "page": "products",
                "click_count": 0,
                "page_visit_count": 0,
                "average_inter_click_ms": 0,
                "form_submission_count": 0,
                "repeated_action_count": 0,
                "request_count": 0,
                "request_frequency_per_minute": 0,
                "session_duration_ms": duration,
                **profile,
            },
        }
        with self.session_factory() as db:
            session = Session(
                attributes=attributes,
                started_at=started_at,
                last_seen_at=now,
            )
            db.add(session)
            db.flush()
            db.add(SessionIdentity(session_id=session.id, public_id=public_id))
            if include_events:
                click_count = int(profile.get("click_count", 0))
                page_count = int(profile.get("page_visit_count", 0))
                form_count = int(profile.get("form_submission_count", 0))
                average_interval = int(profile.get("average_inter_click_ms", 0))
                request_rate = float(profile.get("request_frequency_per_minute", 0))
                event_target = round(request_rate * duration / 60_000)
                fillers = max(0, event_target - click_count - page_count - form_count)
                events = []
                for index in range(click_count):
                    received_at = started_at + timedelta(milliseconds=index * average_interval)
                    action_id = "repeat.action" if profile.get("repeated_action_count", 0) >= 3 else f"click.{index}"
                    events.append(("interaction.click", {"action_id": action_id}, received_at))
                for index in range(page_count):
                    events.append(("navigation.page_view", {"page": f"page.{index}"}, started_at))
                for index in range(form_count):
                    events.append(("interaction.form_submit", {"form_id": f"form.{index}"}, started_at))
                for _ in range(fillers):
                    events.append(("session.start", {}, started_at))
                db.add_all(
                    SecurityEvent(
                        session_id=session.id,
                        event_type=event_type,
                        payload={"data": payload},
                        occurred_at=received_at,
                        received_at=received_at,
                    )
                    for event_type, payload, received_at in events
                )
            db.commit()
        return public_id

    def test_four_server_computed_responses_and_audit_records(self) -> None:
        profiles = [
            ("allow", {"click_count": 1, "session_duration_ms": 60_000}),
            (
                "challenge",
                {
                    "click_count": 2,
                    "page_visit_count": 20,
                    "request_count": 150,
                    "request_frequency_per_minute": 75,
                    "session_duration_ms": 120_000,
                },
            ),
            (
                "delay",
                {
                    "click_count": 30,
                    "page_visit_count": 20,
                    "average_inter_click_ms": 250,
                    "repeated_action_count": 12,
                    "request_frequency_per_minute": 60,
                    "session_duration_ms": 120_000,
                },
            ),
            (
                "block",
                {
                    "click_count": 60,
                    "page_visit_count": 20,
                    "average_inter_click_ms": 100,
                    "form_submission_count": 8,
                    "repeated_action_count": 12,
                    "request_frequency_per_minute": 120,
                    "session_duration_ms": 60_000,
                },
            ),
        ]
        for expected_action, profile in profiles:
            with self.subTest(expected_action=expected_action):
                session_id = self.create_session(profile)
                response = self.client.get(
                    f"/api/session/{session_id}/access?score=0&actual_response=allow"
                )
                self.assertEqual(response.status_code, 200, response.text)
                access = response.json()
                self.assertEqual(access["recommended_action"], expected_action)
                self.assertEqual(access["actual_response"], expected_action)
                self.assertTrue(access["safe_demo_mode"])
                if expected_action == "delay":
                    self.assertEqual(access["delay_ms"], 37)
                if expected_action == "block":
                    blocked = self.client.get("/api/decision/" + access["request_id"])
                    self.assertEqual(blocked.status_code, 200)
                    self.assertEqual(blocked.json()["actual_response"], "block")
                with self.session_factory() as db:
                    session_pk = db.scalar(
                        select(SessionIdentity.session_id).where(SessionIdentity.public_id == session_id)
                    )
                    decisions = db.scalars(
                        select(SecurityDecision).where(
                            SecurityDecision.session_id == session_pk
                        )
                    ).all()
                    self.assertEqual(len(decisions), 1)
                    self.assertEqual(decisions[0].recommended_action, expected_action)
                    self.assertEqual(decisions[0].action, expected_action)
                    self.assertTrue(decisions[0].reason)
                    self.assertIsNotNone(decisions[0].created_at)
                    self.assertEqual(decisions[0].request_id, access["request_id"])

    def test_human_demo_challenge_records_failure_and_pass(self) -> None:
        session_id = self.create_session(
            {
                "click_count": 2,
                "page_visit_count": 20,
                "request_count": 150,
                "request_frequency_per_minute": 75,
                "session_duration_ms": 120_000,
            }
        )
        access = self.client.get(f"/api/session/{session_id}/access").json()
        challenge_response = self.client.post(f"/api/session/{session_id}/challenge")
        self.assertEqual(challenge_response.status_code, 200, challenge_response.text)
        challenge = challenge_response.json()
        self.assertIn("not a production CAPTCHA", challenge["notice"])
        operands = re.search(r"(\d+) \+ (\d+)", challenge["question"])
        self.assertIsNotNone(operands)
        answer = str(int(operands.group(1)) + int(operands.group(2)))
        verify_path = f"/api/session/{session_id}/challenge/{challenge['challenge_id']}/verify"

        failed = self.client.post(verify_path, json={"answer": "999"})
        self.assertEqual(failed.status_code, 422)
        verified = self.client.post(verify_path, json={"answer": answer})
        self.assertEqual(verified.status_code, 200, verified.text)
        self.assertTrue(verified.json()["verified"])
        self.assertEqual(verified.json()["actual_response"], "allow")
        self.assertEqual(access["recommended_action"], "challenge")

        details = self.client.get(f"/api/dashboard/sessions/{session_id}").json()
        self.assertEqual(details["recommended_action"], "challenge")
        self.assertEqual(details["actual_response"], "allow")
        self.assertEqual(len(details["decision_history"]), 3)
        self.assertEqual(details["decision_history"][0]["actual_response"], "allow")
        self.assertTrue(any("not accepted" in item["reason"] for item in details["decision_history"]))

    def test_client_feature_snapshot_cannot_raise_risk_without_observed_events(self) -> None:
        session_id = self.create_session(
            {
                "click_count": 1000,
                "page_visit_count": 1000,
                "request_count": 1000,
                "request_frequency_per_minute": 1000,
                "average_inter_click_ms": 1,
                "repeated_action_count": 1000,
                "session_duration_ms": 60_000,
            },
            include_events=False,
        )
        access = self.client.get(f"/api/session/{session_id}/access").json()
        self.assertEqual(access["risk_score"], 0)
        self.assertEqual(access["recommended_action"], "allow")
        self.assertEqual(access["actual_response"], "allow")

    def test_loaded_ml_prediction_is_returned_persisted_and_combined(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_path = f"{directory}/behavior-model.joblib"
            train_model(artifact_path, samples=400, seed=31)
            self.settings.ml_model_path = artifact_path
            session_id = self.create_session(
                {
                    "click_count": 60,
                    "page_visit_count": 20,
                    "average_inter_click_ms": 100,
                    "form_submission_count": 8,
                    "repeated_action_count": 12,
                    "request_frequency_per_minute": 120,
                    "session_duration_ms": 60_000,
                }
            )
            response = self.client.get(f"/api/session/{session_id}/access")
            self.assertEqual(response.status_code, 200, response.text)
            access = response.json()
            self.assertIsNotNone(access["ml_prediction"])
            self.assertEqual(access["ml_prediction"]["prediction"], "suspicious")
            self.assertIn("ml_suspicious_probability", [signal["name"] for signal in access["signals"]])

            details = self.client.get(f"/api/dashboard/sessions/{session_id}").json()
            self.assertEqual(details["ml_prediction"], access["ml_prediction"])

    def test_admin_review_requires_auth_and_appends_override(self) -> None:
        session_id = self.create_session(
            {
                "click_count": 60,
                "page_visit_count": 20,
                "average_inter_click_ms": 100,
                "form_submission_count": 8,
                "repeated_action_count": 12,
                "request_frequency_per_minute": 120,
                "session_duration_ms": 60_000,
            }
        )
        initial = self.client.get(f"/api/session/{session_id}/access").json()
        self.assertEqual(initial["recommended_action"], "block")
        path = f"/api/admin/sessions/{session_id}/review"
        body = {"actual_response": "allow", "notes": "Reviewed simulated session"}
        unauthorized = self.client.post(path, json=body)
        self.assertEqual(unauthorized.status_code, 401)
        forged = self.client.post(
            path,
            headers={"Authorization": "Bearer " + self.settings.admin_api_key},
            json={**body, "risk_score": 0},
        )
        self.assertEqual(forged.status_code, 422)
        reviewed = self.client.post(
            path,
            headers={"Authorization": "Bearer " + self.settings.admin_api_key},
            json=body,
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        decision = reviewed.json()["decision"]
        self.assertEqual(decision["recommended_action"], "block")
        self.assertEqual(decision["actual_response"], "allow")
        self.assertEqual(decision["decision_source"], "admin_review")
        details = self.client.get(f"/api/dashboard/sessions/{session_id}").json()
        self.assertEqual(details["actual_response"], "allow")
        self.assertEqual(details["decision_history"][0]["reviewed_by"], "administrator")
        self.assertEqual(details["decision_history"][0]["review_notes"], "")
        self.assertNotIn("Reviewed simulated session", str(details["decision_history"]))

    def test_invalid_admin_token_and_challenge_attempts_do_not_leak_secrets(self) -> None:
        session_id = self.create_session({"click_count": 1})
        missing = self.client.post(
            f"/api/admin/sessions/{session_id}/review",
            headers={"Authorization": "Bearer wrong-token"},
            json={"actual_response": "allow"},
        )
        self.assertEqual(missing.status_code, 401)
        self.assertNotIn(self.settings.admin_api_key, missing.text)
        invalid_session = self.client.get("/api/session/" + str(uuid4()) + "/access")
        self.assertEqual(invalid_session.status_code, 404)
        self.assertNotIn("events", invalid_session.text.lower())


if __name__ == "__main__":
    unittest.main()
