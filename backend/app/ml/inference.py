"""Optional local classifier trained on synthetic behavior profiles."""

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.ml.synthetic_data import FEATURE_NAMES, features_to_vector, generate_synthetic_dataset

DATASET_TYPE = "synthetic_behavior_profiles"
MODEL_TYPE = "StandardScaler + LogisticRegression"


@dataclass(frozen=True)
class ModelArtifact:
    model: Pipeline
    metadata: dict[str, Any]


def default_artifact_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "behavior_model.joblib"


def train_model(
    artifact_path: str | Path | None = None,
    samples: int = 2000,
    seed: int = 2026,
) -> dict[str, Any]:
    features, labels = generate_synthetic_dataset(samples=samples, seed=seed)
    x_train, x_test, y_train, y_test = train_test_split(
        np.asarray(features, dtype=float),
        np.asarray(labels),
        test_size=0.25,
        random_state=seed,
        stratify=labels,
    )
    model = Pipeline(
        steps=[
            ("scale", StandardScaler()),
            ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=seed)),
        ]
    )
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    probabilities = model.predict_proba(x_test)[:, list(model.classes_).index("suspicious")]
    metrics = {
        "accuracy": float(accuracy_score(y_test, predictions)),
        "precision": float(precision_score(y_test, predictions, pos_label="suspicious", zero_division=0)),
        "recall": float(recall_score(y_test, predictions, pos_label="suspicious", zero_division=0)),
        "f1": float(f1_score(y_test, predictions, pos_label="suspicious", zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test == "suspicious", probabilities)),
    }
    metadata = {
        "model_type": MODEL_TYPE,
        "training_dataset_type": DATASET_TYPE,
        "training_status": "completed",
        "sample_count": samples,
        "seed": seed,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_names": list(FEATURE_NAMES),
        "classes": [str(label) for label in model.classes_],
        "evaluation_metrics": metrics,
        "metrics_note": "Held-out synthetic test split; does not estimate real-world accuracy.",
    }
    path = Path(artifact_path) if artifact_path else default_artifact_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "metadata": metadata}, path)
    clear_model_cache()
    return metadata


@lru_cache(maxsize=4)
def _load_cached(artifact_path: str, modified_ns: int) -> ModelArtifact:
    del modified_ns
    bundle = joblib.load(artifact_path)
    if not isinstance(bundle, dict) or not isinstance(bundle.get("metadata"), dict):
        raise ValueError("Model artifact format is invalid")
    model = bundle.get("model")
    metadata = bundle["metadata"]
    if metadata.get("feature_names") != list(FEATURE_NAMES):
        raise ValueError("Model artifact feature contract does not match this application")
    return ModelArtifact(model=model, metadata=metadata)


def load_model(artifact_path: str | Path | None = None) -> ModelArtifact | None:
    path = Path(artifact_path) if artifact_path else default_artifact_path()
    if not path.is_file():
        return None
    try:
        return _load_cached(str(path.resolve()), path.stat().st_mtime_ns)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("Model artifact could not be loaded") from exc


def clear_model_cache() -> None:
    _load_cached.cache_clear()


def get_model_status(artifact_path: str | Path | None = None) -> dict[str, Any]:
    try:
        artifact = load_model(artifact_path)
    except ValueError:
        return {
            "loaded": False,
            "model_type": "Artifact unavailable",
            "training_dataset_type": DATASET_TYPE,
            "evaluation_metrics": None,
            "last_training_status": "Artifact failed validation",
            "metrics_note": "Synthetic test metrics are not real-world accuracy estimates.",
        }
    if artifact is None:
        return {
            "loaded": False,
            "model_type": "Not trained",
            "training_dataset_type": DATASET_TYPE,
            "evaluation_metrics": None,
            "last_training_status": "No local model artifact found",
            "metrics_note": "Train with synthetic data; metrics do not estimate real-world accuracy.",
        }
    return {
        "loaded": True,
        "model_type": artifact.metadata["model_type"],
        "training_dataset_type": artifact.metadata["training_dataset_type"],
        "evaluation_metrics": artifact.metadata["evaluation_metrics"],
        "last_training_status": f"Trained {artifact.metadata['trained_at']} on {artifact.metadata['sample_count']} synthetic rows",
        "metrics_note": artifact.metadata["metrics_note"],
    }


def predict_behavior(features: dict[str, Any], artifact: ModelArtifact | None) -> dict[str, Any] | None:
    if artifact is None:
        return None
    vector = np.asarray([features_to_vector(features)], dtype=float)
    probabilities = artifact.model.predict_proba(vector)[0]
    probability_by_class = {
        str(label): float(probability)
        for label, probability in zip(artifact.model.classes_, probabilities)
    }
    suspicious_probability = probability_by_class.get("suspicious", 0.0)
    return {
        "prediction": "suspicious" if suspicious_probability >= 0.5 else "normal",
        "suspicious_probability": suspicious_probability,
        "probabilities": probability_by_class,
        "model_type": artifact.metadata["model_type"],
        "training_dataset_type": artifact.metadata["training_dataset_type"],
        "evaluation_metrics": artifact.metadata["evaluation_metrics"],
        "metrics_note": artifact.metadata["metrics_note"],
    }