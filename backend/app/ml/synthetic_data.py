"""Deterministic synthetic behavioral profiles for local prototype training only."""

from random import Random
from typing import Any

FEATURE_NAMES = (
    "click_count",
    "page_visit_count",
    "average_inter_click_ms",
    "form_submission_count",
    "repeated_form_submission_count",
    "repeated_action_count",
    "request_count",
    "request_frequency_per_minute",
    "session_duration_ms",
)


def generate_synthetic_dataset(samples: int = 2000, seed: int = 2026) -> tuple[list[list[float]], list[str]]:
    if samples < 100 or samples % 2:
        raise ValueError("samples must be an even number of at least 100")

    random = Random(seed)
    features: list[list[float]] = []
    labels: list[str] = []
    for index in range(samples):
        duration_ms = random.randint(30_000, 600_000)
        if index % 2 == 0:
            clicks = random.randint(0, 18)
            pages = random.randint(1, 12)
            forms = random.choices([0, 1, 2], weights=[0.66, 0.28, 0.06])[0]
            repeated_forms = 0
            repeated_actions = random.randint(0, 2)
            request_count = random.randint(5, 90)
            average_interval = random.randint(1_500, 30_000) if clicks > 1 else 0
            label = "normal"
        else:
            pattern = (index // 2) % 4
            if pattern == 0:
                clicks, pages, forms = random.randint(40, 120), random.randint(10, 35), random.randint(0, 2)
                repeated_forms = 0
                repeated_actions = random.randint(12, 55)
                request_count = random.randint(80, 220)
                average_interval = random.randint(40, 400)
            elif pattern == 1:
                clicks, pages, forms = random.randint(1, 8), random.randint(30, 100), 0
                repeated_forms = repeated_actions = 0
                request_count = random.randint(120, 300)
                average_interval = random.randint(0, 2_000)
            elif pattern == 2:
                clicks, pages, forms = random.randint(10, 50), random.randint(2, 15), random.randint(5, 25)
                repeated_forms = max(2, forms - random.randint(0, 2))
                repeated_actions = random.randint(5, 30)
                request_count = random.randint(40, 180)
                average_interval = random.randint(100, 1_000)
            else:
                clicks, pages, forms = random.randint(8, 45), random.randint(5, 25), random.randint(0, 4)
                repeated_forms = 0
                repeated_actions = random.randint(3, 25)
                request_count = random.randint(45, 180)
                average_interval = random.randint(100, 1_200)
            label = "suspicious"

        request_rate = request_count * 60_000 / duration_ms
        features.append(
            [float(value) for value in (
                clicks, pages, average_interval, forms, repeated_forms, repeated_actions,
                request_count, request_rate, duration_ms,
            )]
        )
        labels.append(label)
    return features, labels


def features_to_vector(features: dict[str, Any]) -> list[float]:
    return [float(features.get(name, 0) or 0) for name in FEATURE_NAMES]