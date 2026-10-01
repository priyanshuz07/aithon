from math import ceil
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request

_WINDOW_SECONDS = 60.0
_SESSION_START_LIMIT = 30
_EVENT_BATCH_LIMIT = 120
_DEMO_SCENARIO_LIMIT = 12
_windows: dict[tuple[str, str], tuple[float, int]] = {}
_windows_lock = Lock()


def _check_limit(request: Request, bucket: str, limit: int) -> None:
    client_host = request.client.host if request.client else "unknown"
    key = (client_host, bucket)
    now = monotonic()

    with _windows_lock:
        window_start, count = _windows.get(key, (now, 0))
        if now - window_start >= _WINDOW_SECONDS:
            window_start, count = now, 0
        if count >= limit:
            retry_after = max(1, ceil(_WINDOW_SECONDS - (now - window_start)))
            raise HTTPException(
                status_code=429,
                detail="Too many requests; retry later",
                headers={"Retry-After": str(retry_after)},
            )
        _windows[key] = (window_start, count + 1)

        if len(_windows) > 4096:
            expired = [
                rate_key
                for rate_key, (started, _) in _windows.items()
                if now - started >= _WINDOW_SECONDS
            ]
            for rate_key in expired:
                _windows.pop(rate_key, None)


def limit_session_starts(request: Request) -> None:
    _check_limit(request, "session-start", _SESSION_START_LIMIT)


def limit_event_batches(request: Request) -> None:
    _check_limit(request, "event-batch", _EVENT_BATCH_LIMIT)


def limit_demo_scenarios(request: Request) -> None:
    _check_limit(request, "demo-scenario", _DEMO_SCENARIO_LIMIT)
