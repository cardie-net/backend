"""CORS must never reflect arbitrary origins while credentials are allowed."""

import pytest
from httpx import AsyncClient

from src.config import Settings, settings

ALLOWED_ORIGIN = settings.FRONTEND_URL
DISALLOWED_ORIGIN = "https://evil.example"


@pytest.mark.asyncio
async def test_simple_request_from_allowed_origin(async_client: AsyncClient):
    response = await async_client.get(
        "/api/v1/community", headers={"Origin": ALLOWED_ORIGIN}
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.asyncio
async def test_simple_request_from_unknown_origin_gets_no_cors_headers(
    async_client: AsyncClient,
):
    response = await async_client.get(
        "/api/v1/community", headers={"Origin": DISALLOWED_ORIGIN}
    )

    assert response.status_code == 200
    # Starlette always emits Access-Control-Allow-Credentials on simple
    # headers; without Access-Control-Allow-Origin the browser still discards
    # the response, so the missing origin header is the actual guard.
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_preflight_from_allowed_origin(async_client: AsyncClient):
    response = await async_client.options(
        "/api/v1/community",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


@pytest.mark.asyncio
async def test_preflight_from_unknown_origin_is_rejected(async_client: AsyncClient):
    response = await async_client.options(
        "/api/v1/community",
        headers={
            "Origin": DISALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_defaults_to_frontend_url():
    configured = Settings(
        SECRET_KEY="test-key",
        FRONTEND_URL="https://cardie.example",
        CORS_ALLOW_ORIGINS="",
    )

    assert configured.cors_origins == ["https://cardie.example"]


def test_cors_origins_parses_list_and_drops_wildcards():
    configured = Settings(
        SECRET_KEY="test-key",
        CORS_ALLOW_ORIGINS=" * , https://app.example.com ,, http://localhost:3000 ",
    )

    assert configured.cors_origins == [
        "https://app.example.com",
        "http://localhost:3000",
    ]
