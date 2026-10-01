from starlette.responses import JSONResponse


class RequestSizeLimitMiddleware:
    def __init__(self, app, max_body_bytes: int = 65_536) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope.get("path") not in {
            "/api/events",
            "/api/session/start",
        } or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_bytes:
                    await self._too_large(scope, receive, send)
                    return
            except ValueError:
                await JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header"},
                )(scope, receive, send)
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_body_bytes:
                await self._too_large(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        body_bytes = bytes(body)
        delivered = False

        async def replay_body():
            nonlocal delivered
            if delivered:
                return {"type": "http.disconnect"}
            delivered = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        await self.app(scope, replay_body, send)

    async def _too_large(self, scope, receive, send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": f"Request body exceeds {self.max_body_bytes} bytes"},
        )
        await response(scope, receive, send)
