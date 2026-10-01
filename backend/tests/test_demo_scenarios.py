import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.demo import router as demo_router
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.ml.inference import train_model


class DemoScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.settings = Settings(safe_demo_mode=True, demo_challenge_secret="demo-test-challenge-secret-1234567890")
        self.app = FastAPI()
        self.app.include_router(demo_router)
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

    def test_all_fixed_scenarios_generate_database_backed_outcomes(self) -> None:
        expected = {
            "normal": ("low", "normal_browsing", "allow"),
            "automated": ("medium", "repetitive_scraping_like_behavior", "challenge"),
            "high_frequency": ("high", "automated_browsing", "delay"),
            "critical": ("critical", "automated_form_submission", "block"),
        }
        with tempfile.TemporaryDirectory() as directory:
            artifact_path = f"{directory}/demo-model.joblib"
            train_model(artifact_path, samples=400, seed=41)
            self.settings.ml_model_path = artifact_path
            for scenario, (risk_level, category, action) in expected.items():
                with self.subTest(scenario=scenario):
                    response = self.client.post(f"/api/demo/scenarios/{scenario}")
                    self.assertEqual(response.status_code, 200, response.text)
                    result = response.json()
                    self.assertEqual(result["scenario"], scenario)
                    self.assertEqual(result["risk_level"], risk_level)
                    self.assertEqual(result["estimated_behavioral_category"], category)
                    self.assertEqual(result["recommended_action"], action)
                    self.assertEqual(result["actual_response"], action)
                    self.assertTrue(result["ml_prediction"])
                    self.assertTrue(result["explanation"])
                    details = self.client.get(
                        f"/api/dashboard/sessions/{result['session_id']}"
                    ).json()
                    self.assertEqual(details["risk_score"], result["score"])
                    self.assertEqual(details["rule_signals"], result["signals"])
                    self.assertEqual(details["ml_prediction"], result["ml_prediction"])
                    self.assertEqual(details["recommended_action"], action)
                    self.assertEqual(details["actual_response"], action)

    def test_only_named_synthetic_scenarios_are_accepted(self) -> None:
        response = self.client.post("/api/demo/scenarios/custom?score=100&actual_response=block")
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
