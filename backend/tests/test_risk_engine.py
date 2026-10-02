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
        self.assertEqual(result.behavioral_factors["request_frequency"]["level"], "low")
        self.assertEqual(result.behavioral_factors["action_repetition"]["level"], "low")
        self.assertEqual(result.behavioral_factors["timing_variation"]["status"], "insufficient_data")
        self.assertEqual(result.behavioral_factors["navigation_pattern"]["status"], "normal")

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

    def test_repeated_actions_timing_navigation_and_requests_raise_risk(self) -> None:
        features = {
            "click_count": 20,
            "page_visit_count": 20,
            "repeated_page_visit_count": 19,
            "average_inter_click_ms": 50,
            "repeated_action_count": 19,
            "request_count": 100,
            "request_frequency_per_minute": 50,
            "session_duration_ms": 120_000,
            "meaningful_event_count": 40,
        }

        first = analyze_behavior(features)
        second = analyze_behavior(features)

        self.assertEqual(first.score, 70)
        self.assertEqual(first, second)
        self.assertEqual(first.risk_level, "high")
        self.assertEqual(first.estimated_behavioral_category, "repetitive_navigation")
        self.assertEqual(first.recommended_response, "delay")
        self.assertIn("repeated_page_visits", [signal["name"] for signal in first.signals])

    def test_missing_click_interval_does_not_add_timing_risk(self) -> None:
        result = analyze_behavior(
            {
                "click_count": 5,
                "average_inter_click_ms": 0,
                "session_duration_ms": 120_000,
                "meaningful_event_count": 5,
            }
        )

        self.assertEqual(result.score, 0)
        self.assertNotIn("average_time_between_clicks", [signal["name"] for signal in result.signals])

    def test_repeated_navigation_transition_is_explained(self) -> None:
        result = analyze_behavior(
            {
                "page_visit_count": 6,
                "repeated_navigation_transition_count": 4,
                "session_duration_ms": 120_000,
                "meaningful_event_count": 6,
            }
        )

        self.assertEqual(result.score, 8)
        self.assertEqual(result.risk_level, "low")
        self.assertEqual(result.estimated_behavioral_category, "repetitive_navigation")
        self.assertIn("repeated_navigation_sequence", [signal["name"] for signal in result.signals])

    def test_suspicious_factors_match_contributing_signals(self) -> None:
        result = analyze_behavior(
            {
                "click_count": 8,
                "page_visit_count": 6,
                "repeated_action_count": 8,
                "repeated_page_visit_count": 4,
                "repeated_navigation_transition_count": 4,
                "average_inter_click_ms": 500,
                "timing_interval_count": 7,
                "timing_variation_coefficient": 0.04,
                "request_count": 150,
                "request_frequency_per_minute": 75,
                "session_duration_ms": 120_000,
                "meaningful_event_count": 14,
            }
        )

        self.assertEqual(result.behavioral_factors["request_frequency"]["level"], "high")
        self.assertEqual(result.behavioral_factors["action_repetition"]["level"], "high")
        self.assertEqual(result.behavioral_factors["timing_variation"]["status"], "abnormal")
        self.assertEqual(result.behavioral_factors["navigation_pattern"]["status"], "abnormal")
        self.assertIn("average_time_between_clicks", [signal["name"] for signal in result.signals])
        self.assertIn("repeated_navigation_sequence", [signal["name"] for signal in result.signals])


if __name__ == "__main__":
    unittest.main()