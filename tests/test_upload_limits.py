import pytest

from src.config import settings
from src.middleware import MULTIPART_OVERHEAD_BYTES, UploadSizeLimitMiddleware


def _multipart_scope(
    *,
    method: str = "POST",
    content_length: int | None = None,
    content_type: str = "multipart/form-data; boundary=test",
) -> dict:
    headers = [(b"content-type", content_type.encode("latin-1"))]
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode("latin-1")))
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": "/api/v1/decks/00000000-0000-0000-0000-000000000000/images",
        "raw_path": b"/api/v1/decks/00000000-0000-0000-0000-000000000000/images",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("test", 123),
        "server": ("test", 80),
    }


class _SendRecorder:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int:
        return self.messages[0]["status"]

    @property
    def body(self) -> bytes:
        return b"".join(
            message.get("body", b"")
            for message in self.messages
            if message["type"] == "http.response.body"
        )


@pytest.mark.asyncio
async def test_content_length_over_limit_is_rejected_without_reading_body(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 1024)
    limit = settings.MAX_UPLOAD_SIZE + MULTIPART_OVERHEAD_BYTES
    downstream_called = False

    async def downstream(scope, receive, send):
        nonlocal downstream_called
        downstream_called = True

    async def receive():
        raise AssertionError("the request body must not be read")

    sent = _SendRecorder()
    middleware = UploadSizeLimitMiddleware(downstream)

    await middleware(_multipart_scope(content_length=limit + 1), receive, sent)

    assert downstream_called is False
    assert sent.status == 413
    assert b'"detail":"File too large"' in sent.body
    assert f'"max_size":{settings.MAX_UPLOAD_SIZE}'.encode() in sent.body


@pytest.mark.asyncio
async def test_chunked_multipart_body_over_limit_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 1024)
    limit = settings.MAX_UPLOAD_SIZE + MULTIPART_OVERHEAD_BYTES
    chunks = [b"x" * (limit // 2 + 1), b"x" * (limit // 2 + 1)]
    chunk_index = 0

    async def downstream(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        nonlocal chunk_index
        if chunk_index < len(chunks):
            body = chunks[chunk_index]
            chunk_index += 1
            return {"type": "http.request", "body": body, "more_body": True}
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = _SendRecorder()
    middleware = UploadSizeLimitMiddleware(downstream)

    await middleware(_multipart_scope(), receive, sent)

    assert sent.status == 413
    assert sent.body


@pytest.mark.asyncio
async def test_multipart_body_under_limit_passes_through(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 1024)
    body = b"x" * 100

    async def downstream(scope, receive, send):
        received = 0
        while True:
            message = await receive()
            received += len(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send(
            {"type": "http.response.body", "body": str(received).encode("ascii")}
        )

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    sent = _SendRecorder()
    middleware = UploadSizeLimitMiddleware(downstream)

    await middleware(_multipart_scope(), receive, sent)

    assert sent.status == 200
    assert sent.body == b"100"


@pytest.mark.asyncio
async def test_non_multipart_request_is_not_limited(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE", 10)
    body = b"x" * (MULTIPART_OVERHEAD_BYTES * 2)

    async def downstream(scope, receive, send):
        message = await receive()
        assert message["body"] == body
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    sent = _SendRecorder()
    middleware = UploadSizeLimitMiddleware(downstream)

    await middleware(
        _multipart_scope(content_length=len(body), content_type="application/json"),
        receive,
        sent,
    )

    assert sent.status == 200
