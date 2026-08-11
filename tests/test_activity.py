import pytest
from httpx import AsyncClient


@pytest.fixture
async def user_session(async_client: AsyncClient) -> str:
    response = await async_client.post("/api/v1/auth/guest")
    return response.cookies.get("cardie_session")


@pytest.mark.asyncio
async def test_record_and_get_user_activity(
    async_client: AsyncClient, user_session: str
):
    headers = {"X-Test-Cookie": user_session}

    # 1. Fetch initial activity summary
    res = await async_client.get("/api/v1/users/me/activity", headers=headers)
    assert res.status_code == 200
    summary = res.json()
    assert summary["total_points"] == 0
    assert summary["current_streak"] == 0
    assert summary["longest_streak"] == 0
    assert len(summary["activities"]) == 0

    # 2. Record points for today (learn mode)
    res = await async_client.post(
        "/api/v1/users/me/activity",
        headers=headers,
        json={"points": 12, "count": 3, "activity_type": "learn"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["points"] == 12
    assert data["activities_count"] == 3
    assert data["details"] == {"learn": 12}

    # 3. Record additional points for today (srs mode)
    res = await async_client.post(
        "/api/v1/users/me/activity",
        headers=headers,
        json={"points": 6, "count": 2, "activity_type": "srs"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["points"] == 18
    assert data["activities_count"] == 5
    assert data["details"] == {"learn": 12, "srs": 6}

    # 4. Fetch summary again
    res = await async_client.get("/api/v1/users/me/activity", headers=headers)
    assert res.status_code == 200
    summary = res.json()
    assert summary["total_points"] == 18
    assert summary["current_streak"] == 1
    assert summary["longest_streak"] == 1
    assert len(summary["activities"]) == 1
    assert summary["activities"][0]["points"] == 18


@pytest.mark.asyncio
async def test_unauthenticated_activity_access(async_client: AsyncClient):
    res = await async_client.get("/api/v1/users/me/activity")
    assert res.status_code == 401

    res = await async_client.post(
        "/api/v1/users/me/activity",
        json={"points": 10, "count": 1, "activity_type": "exam"},
    )
    assert res.status_code == 401
