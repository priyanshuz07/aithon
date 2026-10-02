"""Transparent behavioral risk rules; these estimate patterns, not intent."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RiskEngineConfig:
    medium_threshold: int = 30
    high_threshold: int = 60
    critical_threshold: int = 80

    def __post_init__(self) -> None:
        if not 0 < self.medium_threshold < self.high_threshold < self.critical_threshold <= 100:
            raise ValueError("Risk thresholds must be ordered between 1 and 100")


@dataclass(frozen=True)
class RiskAnalysis:
    score: int
    risk_level: str
    estimated_behavioral_category: str
    signals: list[dict[str, Any]] = field(default_factory=list)
    explanation: str = ""
    recommended_response: str = "allow"
    ml_prediction: dict[str, Any] | None = None
    behavioral_factors: dict[str, dict[str, Any]] = field(default_factory=dict)


_RESPONSE_BY_LEVEL = {
    "low": "allow",
    "medium": "challenge",
    "high": "delay",
    "critical": "block",
}


def risk_level_for(score: int, config: RiskEngineConfig = RiskEngineConfig()) -> str:
    if score >= config.critical_threshold:
        return "critical"
    if score >= config.high_threshold:
        return "high"
    if score >= config.medium_threshold:
        return "medium"
    return "low"


def recommended_response_for(risk_level: str) -> str:
    return _RESPONSE_BY_LEVEL[risk_level]


def _rate_per_minute(count: int, duration_ms: int) -> float:
    if duration_ms < 10_000:
        return 0.0
    return count * 60_000 / duration_ms


def score_behavior(
    features: dict[str, Any], ml_prediction: dict[str, Any] | None = None
) -> tuple[int, list[dict[str, Any]]]:
    """Return a capped additive score and the rules that contributed points."""
    clicks = int(features.get("click_count", 0) or 0)
    pages = int(features.get("page_visit_count", 0) or 0)
    forms = int(features.get("form_submission_count", 0) or 0)
    repeated_forms = int(features.get("repeated_form_submission_count", 0) or 0)
    repeated_actions = int(features.get("repeated_action_count", 0) or 0)
    repeated_pages = int(features.get("repeated_page_visit_count", 0) or 0)
    repeated_navigation_transitions = int(features.get("repeated_navigation_transition_count", 0) or 0)
    requests = int(features.get("request_count", 0) or 0)
    duration_ms = int(features.get("session_duration_ms", 0) or 0)
    inter_click_ms = int(features.get("average_inter_click_ms", 0) or 0)
    timing_interval_count = int(features.get("timing_interval_count", 0) or 0)
    timing_variation_coefficient = float(features.get("timing_variation_coefficient", 0) or 0)
    request_rate = float(features.get("request_frequency_per_minute", 0) or 0)
    click_rate = _rate_per_minute(clicks, duration_ms)
    page_rate = _rate_per_minute(pages, duration_ms)
    score = 0
    signals: list[dict[str, Any]] = []

    def add(name: str, points: int, observation: str) -> None:
        nonlocal score
        if points:
            score += points
            signals.append({"name": name, "points": points, "observation": observation})

    if click_rate >= 30:
        add("click_frequency", 16, f"{click_rate:.1f} clicks per minute")
    elif click_rate >= 15:
        add("click_frequency", 10, f"{click_rate:.1f} clicks per minute")
    elif click_rate >= 8:
        add("click_frequency", 5, f"{click_rate:.1f} clicks per minute")

    if clicks >= 5 and 0 < inter_click_ms <= 150:
        add("average_time_between_clicks", 14, f"{inter_click_ms} ms average")
    elif clicks >= 5 and 0 < inter_click_ms <= 350:
        add("average_time_between_clicks", 8, f"{inter_click_ms} ms average")
    elif clicks >= 5 and 0 < inter_click_ms <= 700:
        add("average_time_between_clicks", 3, f"{inter_click_ms} ms average")

    if (
        clicks >= 5
        and timing_interval_count >= 4
        and inter_click_ms > 700
        and timing_variation_coefficient <= 0.1
    ):
        add(
            "consistent_action_timing",
            5,
            f"Low variation across {timing_interval_count} action intervals",
        )

    if page_rate >= 20:
        add("page_visit_frequency", 16, f"{page_rate:.1f} page visits per minute")
    elif page_rate >= 10:
        add("page_visit_frequency", 10, f"{page_rate:.1f} page visits per minute")
    elif page_rate >= 5:
        add("page_visit_frequency", 5, f"{page_rate:.1f} page visits per minute")

    if repeated_forms >= 5:
        add("repeated_form_submissions", 16, f"{repeated_forms} repeated submissions")
    elif repeated_forms >= 3:
        add("repeated_form_submissions", 10, f"{repeated_forms} repeated submissions")
    elif repeated_forms >= 2:
        add("repeated_form_submissions", 5, f"{repeated_forms} repeated submissions")
    elif forms >= 5:
        add("form_submission_frequency", 5, f"{forms} submissions in one session")

    if repeated_actions >= 12:
        add("repeated_actions", 16, f"{repeated_actions} repeat actions")
    elif repeated_actions >= 6:
        add("repeated_actions", 10, f"{repeated_actions} repeat actions")
    elif repeated_actions >= 3:
        add("repeated_actions", 5, f"{repeated_actions} repeat actions")

    if repeated_navigation_transitions >= 6:
        add("repeated_navigation_sequence", 12, f"{repeated_navigation_transitions} repeat navigation transitions")
    elif repeated_navigation_transitions >= 2:
        add("repeated_navigation_sequence", 8, f"{repeated_navigation_transitions} repeat navigation transitions")
    elif repeated_pages >= 8:
        add("repeated_page_visits", 12, f"{repeated_pages} repeat page visits")
    elif repeated_pages >= 4:
        add("repeated_page_visits", 8, f"{repeated_pages} repeat page visits")
    elif repeated_pages >= 2:
        add("repeated_page_visits", 4, f"{repeated_pages} repeat page visits")

    if request_rate >= 120:
        add("request_frequency", 16, f"{request_rate:.1f} requests per minute")
    elif request_rate >= 60:
        add("request_frequency", 10, f"{request_rate:.1f} requests per minute")
    elif request_rate >= 30:
        add("request_frequency", 5, f"{request_rate:.1f} requests per minute")
    elif requests >= 100:
        add("request_volume", 5, f"{requests} requests in one session")

    if duration_ms and duration_ms <= 10_000 and (
        clicks >= 8 or pages >= 5 or request_rate >= 30
    ):
        add("short_high_activity_session", 8, f"High activity within {duration_ms} ms")

    if page_rate >= 10 and request_rate >= 30 and clicks <= max(3, pages // 3):
        add("page_and_request_burst", 10, "Frequent page visits and requests with few clicks")
    if clicks >= 8 and 0 < inter_click_ms <= 300:
        add("rapid_click_combination", 8, "Frequent clicks paired with short click intervals")
    if repeated_forms >= 3 and request_rate >= 30:
        add("form_and_request_combination", 8, "Repeated form submissions paired with frequent requests")

    if ml_prediction is not None:
        probability = min(1.0, max(0.0, float(ml_prediction.get("suspicious_probability", 0) or 0)))
        if probability >= 0.9:
            add("ml_suspicious_probability", 15, f"Synthetic-model suspicious probability {probability:.0%}")
        elif probability >= 0.75:
            add("ml_suspicious_probability", 10, f"Synthetic-model suspicious probability {probability:.0%}")
        elif probability >= 0.6:
            add("ml_suspicious_probability", 5, f"Synthetic-model suspicious probability {probability:.0%}")

    return min(score, 100), signals


def classify_behavior(features: dict[str, Any], score: int) -> str:
    """Classify observable patterns without asserting a user's actual intent."""
    clicks = int(features.get("click_count", 0) or 0)
    pages = int(features.get("page_visit_count", 0) or 0)
    forms = int(features.get("form_submission_count", 0) or 0)
    repeated_forms = int(features.get("repeated_form_submission_count", 0) or 0)
    repeated_actions = int(features.get("repeated_action_count", 0) or 0)
    repeated_pages = int(features.get("repeated_page_visit_count", 0) or 0)
    repeated_navigation_transitions = int(features.get("repeated_navigation_transition_count", 0) or 0)
    duration_ms = int(features.get("session_duration_ms", 0) or 0)
    inter_click_ms = int(features.get("average_inter_click_ms", 0) or 0)
    request_rate = float(features.get("request_frequency_per_minute", 0) or 0)
    page_rate = _rate_per_minute(pages, duration_ms)
    click_rate = _rate_per_minute(clicks, duration_ms)
    event_count = int(features.get("meaningful_event_count", clicks + pages + forms) or 0)
    account_repetition = bool(features.get("account_related_repetition", False))

    if account_repetition and (repeated_forms or repeated_actions):
        return "suspicious_account_activity"
    if repeated_forms >= 2 and (inter_click_ms <= 1000 or forms >= 4):
        return "automated_form_submission"
    if page_rate >= 5 and request_rate >= 30 and clicks <= max(3, pages // 3):
        return "repetitive_scraping_like_behavior"
    if repeated_pages >= 4 or repeated_navigation_transitions >= 2:
        return "repetitive_navigation"
    if click_rate >= 8 or (request_rate >= 60 and (clicks >= 5 or pages >= 5)):
        return "automated_browsing"
    if event_count < 2 or (score >= 30 and not (clicks or pages or forms or request_rate)):
        return "unknown_or_insufficient_evidence"
    if score < 30 and repeated_actions < 3:
        return "normal_browsing"
    return "unknown_or_insufficient_evidence"


def analyze_behavior(
    features: dict[str, Any],
    config: RiskEngineConfig = RiskEngineConfig(),
    ml_prediction: dict[str, Any] | None = None,
) -> RiskAnalysis:
    score, signals = score_behavior(features, ml_prediction)
    level = risk_level_for(score, config)
    category = classify_behavior(features, score)
    response = recommended_response_for(level)
    behavioral_factors = explain_behavioral_factors(features, signals)
    if signals:
        observations = "; ".join(signal["observation"] for signal in signals)
        explanation = (
            f"Risk score {score}/100 ({level}) from observed signals: {observations}. "
            f"Estimated pattern: {category.replace('_', ' ')}; this is a behavioral estimate, not a claim about intent."
        )
    elif category == "unknown_or_insufficient_evidence":
        explanation = "There is not enough behavioral evidence to estimate a pattern; no risk signals increased the score."
    else:
        explanation = f"No configured risk rules were triggered; observed pattern is consistent with {category.replace('_', ' ')}."
    return RiskAnalysis(
        score=score,
        risk_level=level,
        estimated_behavioral_category=category,
        signals=signals,
        explanation=explanation,
        recommended_response=response,
        ml_prediction=ml_prediction,
        behavioral_factors=behavioral_factors,
    )


def explain_behavioral_factors(
    features: dict[str, Any], signals: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Summarize measured factors without assigning a confidence estimate."""
    request_rate = float(features.get("request_frequency_per_minute", 0) or 0)
    duration_ms = int(features.get("session_duration_ms", 0) or 0)
    requests = int(features.get("request_count", 0) or 0)
    if duration_ms < 10_000:
        request_level = "insufficient_data"
        request_observation = f"{requests} observed requests; rate requires at least 10 seconds of session data"
    else:
        request_level = "low" if request_rate < 30 else "medium" if request_rate < 60 else "high"
        request_observation = f"{request_rate:.1f} observed requests per minute"

    repeated_actions = int(features.get("repeated_action_count", 0) or 0)
    repeated_forms = int(features.get("repeated_form_submission_count", 0) or 0)
    total_repetitions = repeated_actions + repeated_forms
    action_level = "low" if total_repetitions < 2 else "medium" if total_repetitions < 6 else "high"

    clicks = int(features.get("click_count", 0) or 0)
    average_interval = int(features.get("average_inter_click_ms", 0) or 0)
    interval_count = int(features.get("timing_interval_count", max(0, clicks - 1)) or 0)
    variation = features.get("timing_variation_coefficient")
    timing_signals = {
        "average_time_between_clicks",
        "rapid_click_combination",
        "consistent_action_timing",
    }
    timing_measured = clicks >= 5 and interval_count >= 4 and average_interval > 0
    timing_status = "insufficient_data"
    if timing_measured:
        timing_status = "abnormal" if timing_signals.intersection(
            signal["name"] for signal in signals
        ) else "normal"
        variation_text = (
            f"; interval variation {float(variation) * 100:.1f}%"
            if variation is not None
            else ""
        )
        timing_observation = f"{average_interval} ms average across {interval_count} intervals{variation_text}"
    else:
        timing_observation = "At least five clicks with measurable intervals are needed"

    pages = int(features.get("page_visit_count", 0) or 0)
    repeated_pages = int(features.get("repeated_page_visit_count", 0) or 0)
    repeated_transitions = int(features.get("repeated_navigation_transition_count", 0) or 0)
    page_rate = _rate_per_minute(pages, duration_ms)
    navigation_signals = {
        "page_visit_frequency",
        "repeated_page_visits",
        "repeated_navigation_sequence",
        "page_and_request_burst",
    }
    navigation_status = "insufficient_data"
    if pages >= 2:
        navigation_status = "abnormal" if (
            navigation_signals.intersection(signal["name"] for signal in signals)
        ) else "normal"
        navigation_observation = (
            f"{pages} page visits; {repeated_pages} repeated visits; "
            f"{repeated_transitions} repeated transitions; {page_rate:.1f} visits per minute"
        )
    else:
        navigation_observation = "At least two page visits are needed to assess navigation"

    return {
        "request_frequency": {"level": request_level, "observation": request_observation},
        "action_repetition": {
            "level": action_level,
            "observation": f"{repeated_actions} repeated actions and {repeated_forms} repeated form submissions",
        },
        "timing_variation": {"status": timing_status, "observation": timing_observation},
        "navigation_pattern": {"status": navigation_status, "observation": navigation_observation},
    }