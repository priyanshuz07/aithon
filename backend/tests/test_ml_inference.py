import tempfile
import unittest
from pathlib import Path

from app.core.risk_engine import analyze_behavior
from app.ml.inference import get_model_status, load_model, predict_behavior, train_model
from app.ml.synthetic_data import generate_synthetic_dataset


class MlInferenceTests(unittest.TestCase):
    def test_synthetic_dataset_is_deterministic_and_balanced(self) -> None:
        first_x, first_y = generate_synthetic_dataset(samples=100, seed=17)
        second_x, second_y = generate_synthetic_dataset(samples=100, seed=17)
        self.assertEqual(first_x, second_x)
        self.assertEqual(first_y, second_y)
        self.assertEqual(first_y.count("normal"), 50)
        self.assertEqual(first_y.count("suspicious"), 50)

    def test_train_load_predict_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_path = Path(directory) / "synthetic-model.joblib"
            metadata = train_model(artifact_path, samples=200, seed=19)
            artifact = load_model(artifact_path)
            prediction = predict_behavior(
                {
                    "click_count": 65,
                    "page_visit_count": 20,
                    "average_inter_click_ms": 100,
                    "form_submission_count": 8,
                    "repeated_form_submission_count": 6,
                    "repeated_action_count": 20,
                    "request_count": 120,
                    "request_frequency_per_minute": 120,
                    "session_duration_ms": 60_000,
                },
                artifact,
            )
            status = get_model_status(artifact_path)

        self.assertEqual(metadata["training_dataset_type"], "synthetic_behavior_profiles")
        self.assertIn("trained_at", metadata)
        self.assertTrue(status["loaded"])
        self.assertEqual(set(metadata["evaluation_metrics"]), {"accuracy", "precision", "recall", "f1", "roc_auc"})
        self.assertTrue(prediction)
        self.assertIn(prediction["prediction"], ("normal", "suspicious"))
        self.assertGreaterEqual(prediction["suspicious_probability"], 0)
        self.assertLessEqual(prediction["suspicious_probability"], 1)
        self.assertIn("not estimate real-world accuracy", prediction["metrics_note"])

    def test_model_contributes_explainable_bounded_risk(self) -> None:
        features = {"meaningful_event_count": 1}
        model_result = {
            "prediction": "suspicious",
            "suspicious_probability": 0.95,
            "probabilities": {"normal": 0.05, "suspicious": 0.95},
        }
        rules_only = analyze_behavior(features)
        combined = analyze_behavior(features, ml_prediction=model_result)
        self.assertEqual(rules_only.score, 0)
        self.assertEqual(combined.score, 15)
        self.assertEqual(combined.risk_level, "low")
        self.assertEqual(combined.recommended_response, "allow")
        self.assertEqual(combined.signals[0]["name"], "ml_suspicious_probability")
        self.assertEqual(combined.ml_prediction, model_result)


if __name__ == "__main__":
    unittest.main()
