from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import settings

UPLOAD_TOO_LARGE_DETAIL = "File too large"
# Multipart framing (boundaries, part headers) adds a small amount on top of the
# file itself. The endpoint still enforces the exact MAX_UPLOAD_SIZE limit.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


class _RequestBodyTooLarge(Exception):
    pass


def upload_too_large_response() -> JSONResponse:
    """Build the 413 response shared by the middleware and the endpoint guard."""
    return JSONResponse(
        status_code=413,
        content={
            "detail": UPLOAD_TOO_LARGE_DETAIL,
            "max_size": settings.MAX_UPLOAD_SIZE,
        },
    )


class UploadSizeLimitMiddleware:
    """Reject oversized multipart uploads before Starlette spools them to disk."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _is_multipart_upload(scope):
            await self.app(scope, receive, send)
            return

        limit = settings.MAX_UPLOAD_SIZE + MULTIPART_OVERHEAD_BYTES

        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > limit:
                    await upload_too_large_response()(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _RequestBodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            if response_started:
                raise
            await upload_too_large_response()(scope, receive, send)


def _is_multipart_upload(scope: Scope) -> bool:
    if scope["type"] != "http" or scope.get("method") not in {
        "POST",
        "PUT",
        "PATCH",
    }:
        return False
    content_type = Headers(scope=scope).get("content-type", "")
    return content_type.lower().startswith("multipart/form-data")
