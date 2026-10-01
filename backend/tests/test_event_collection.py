"""End-to-end smoke test for the local behavior collection API."""

import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

API_BASE_URL = os.environ.get("ABF_API_BASE_URL", "http://127.0.0.1:8000/api").rstrip("/")


def request_json(method: str, path: str, payload: object | None = None) -> tuple[int, dict]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        API_BASE_URL + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urlopen(request, timeout=10) as response:
            content = response.read()
            return response.status, json.loads(content) if content else {}
    except HTTPError as error:
        content = error.read()
        return error.code, json.loads(content) if content else {}
    except URLError as error:
        raise RuntimeError(
            f"Could not reach {API_BASE_URL}; start the FastAPI server first"
        ) from error


def new_event(event_type: str, payload: dict) -> dict:
    return {
        "event_id": str(uuid4()),
        "type": event_type,
        "at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def main() -> None:
    status_code, health = request_json("GET", "/health")
    assert status_code == 200 and health["status"] == "ok", health
    print("PASS health endpoint")

    session_id = str(uuid4())
    start_body = {"session_id": session_id, "sdk_version": "smoke-test.1"}
    status_code, started = request_json("POST", "/session/start", start_body)
    assert status_code == 201 and started["created"] is True, started
    assert started["session_id"] == session_id

    status_code, repeated_start = request_json("POST", "/session/start", start_body)
    assert status_code == 200 and repeated_start["created"] is False, repeated_start
    assert repeated_start["started_at"] == started["started_at"]
    print("PASS random session creation and idempotent start")

    events = [
        new_event("session.start", {"sdk_session_id": session_id, "sdk_version": "smoke-test.1"}),
        new_event("navigation.page_view", {"page": "products"}),
        new_event("interaction.click", {"action_id": "cart.add.gateway"}),
        new_event("interaction.form_submit", {"form_id": "form.activity"}),
    ]
    batch = {
        "session_id": session_id,
        "batch_id": str(uuid4()),
        "events": events,
        "features": {
            "page": "products",
            "click_count": 1,
            "page_visit_count": 1,
            "form_submission_count": 1,
        },
    }
    status_code, accepted = request_json("POST", "/events", batch)
    assert status_code == 201 and accepted["accepted_count"] == len(events), accepted

    status_code, repeated_batch = request_json("POST", "/events", batch)
    assert status_code == 200 and repeated_batch["accepted_count"] == 0, repeated_batch
    assert repeated_batch["duplicate_count"] == len(events), repeated_batch
    print("PASS event batch storage and duplicate suppression")

    status_code, summary = request_json("GET", "/session/" + session_id)
    assert status_code == 200 and summary["event_count"] == len(events), summary
    assert summary["event_type_counts"]["interaction.click"] == 1
    assert summary["latest_features"]["click_count"] == 1
    assert "attributes" not in summary and "user_agent" not in summary
    print("PASS privacy-limited session summary")

    status_code, analysis = request_json("POST", "/session/" + session_id + "/analyze")
    assert status_code == 200, analysis
    assert analysis["score"] == 0 and analysis["risk_level"] == "low", analysis
    assert analysis["estimated_behavioral_category"] == "normal_browsing", analysis
    assert analysis["recommended_response"] == "allow", analysis
    assert analysis["signals"] == [], analysis
    print("PASS stored-event risk analysis and adaptive response")

    status_code, dashboard = request_json("GET", "/dashboard/summary?limit=500")
    assert status_code == 200, dashboard
    dashboard_session = next(
        (item for item in dashboard["sessions"] if item["session_id"] == session_id), None
    )
    assert dashboard_session is not None, dashboard
    assert dashboard_session["click_count"] == 1, dashboard_session
    assert dashboard_session["risk_score"] == analysis["score"], dashboard_session
    assert dashboard_session["response"] == analysis["recommended_response"], dashboard_session
    assert dashboard["total_sessions"] >= len(dashboard["sessions"]), dashboard
    assert isinstance(dashboard["model_status"]["loaded"], bool), dashboard["model_status"]

    status_code, details = request_json("GET", "/dashboard/sessions/" + session_id)
    assert status_code == 200, details
    assert details["event_count"] == len(events), details
    assert details["features"]["click_count"] == 1, details
    assert details["risk_score"] == analysis["score"], details
    assert details["rule_signals"] == analysis["signals"], details
    assert details["actual_response"] == analysis["recommended_response"], details
    assert details["ml_prediction"] == analysis["ml_prediction"], details
    print("PASS dashboard metrics and selected session details match stored records")

    invalid_event = new_event("interaction.form_submit", {"email": "not-stored@example.test"})
    invalid_body = {"session_id": session_id, "events": [invalid_event]}
    status_code, invalid_response = request_json("POST", "/events", invalid_body)
    assert status_code == 422, f"Sensitive/malformed payload should be rejected, got {status_code}"
    assert "not-stored@example.test" not in json.dumps(invalid_response), invalid_response
    print("PASS malformed and sensitive-shaped payload rejection")

    status_code, missing_fields = request_json("POST", "/events", {"session_id": session_id})
    assert status_code == 422, f"Missing event fields should return 422, got {status_code}"
    assert "events" in json.dumps(missing_fields), missing_fields
    print("PASS missing required request fields rejected")

    oversized = json.dumps({"padding": "x" * 66_000}).encode("utf-8")
    oversized_request = Request(
        API_BASE_URL + "/events",
        data=oversized,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(oversized_request, timeout=10) as response:
            oversized_status = response.status
    except HTTPError as error:
        oversized_status = error.code
    assert oversized_status == 413, f"Oversized request should return 413, got {oversized_status}"
    print("PASS oversized request rejection")

    print(f"PASS all collection checks (session {session_id}, {len(events)} stored events)")


if __name__ == "__main__":
    main()
