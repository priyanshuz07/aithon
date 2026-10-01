import unittest

from app.core.risk_engine import RiskEngineConfig, analyze_behavior


class RiskEngineTests(unittest.TestCase):
    def test_normal_browsing_is_low_risk_and_allowed(self) -> None:
        result = analyze_behavior(
            {
                "click_count": 4,
                "page_visit_count": 3,
                "page_time_ms": 120_000,
                "average_inter_click_ms": 8_000,
                "form_submission_count": 1,
                "repeated_action_count": 0,
                "request_count": 12,
                "request_frequency_per_minute": 6,
                "session_duration_ms": 120_000,
                "meaningful_event_count": 8,
            }
        )

        self.assertEqual(result.score, 0)
        self.assertEqual(result.risk_level, "low")
        self.assertEqual(result.estimated_behavioral_category, "normal_browsing")
        self.assertEqual(result.recommended_response, "allow")
        self.assertEqual(result.signals, [])

    def test_repetitive_scraping_pattern_accumulates_explainable_risk(self) -> None:
        result = analyze_behavior(
            {
                "click_count": 2,
                "page_visit_count": 20,
                "form_submission_count": 0,
                "repeated_action_count": 0,
                "request_count": 150,
                "request_frequency_per_minute": 75,
                "session_duration_ms": 120_000,
                "meaningful_event_count": 22,
            }
        )

        self.assertEqual(result.score, 30)
        self.assertEqual(result.risk_level, "medium")
        self.assertEqual(result.estimated_behavioral_category, "repetitive_scraping_like_behavior")
        self.assertEqual(result.recommended_response, "challenge")
        self.assertEqual(
            [signal["name"] for signal in result.signals],
            ["page_visit_frequency", "request_frequency", "page_and_request_burst"],
        )
        self.assertIn("behavioral estimate", result.explanation)

    def test_thresholds_are_configurable(self) -> None:
        result = analyze_behavior(
            {
                "click_count": 2,
                "page_visit_count": 20,
                "request_count": 150,
                "request_frequency_per_minute": 75,
                "session_duration_ms": 120_000,
                "meaningful_event_count": 22,
            },
            RiskEngineConfig(medium_threshold=40, high_threshold=60, critical_threshold=80),
        )
        self.assertEqual(result.score, 30)
        self.assertEqual(result.risk_level, "low")
        self.assertEqual(result.recommended_response, "allow")


if __name__ == "__main__":
    unittest.main()