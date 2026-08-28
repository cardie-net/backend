import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_community_empty(async_client: AsyncClient):
    response = await async_client.get("/api/v1/community")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["total_pages"] == 1
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_community_privacy_isolation(async_client: AsyncClient, user_token: str):
    headers = {"x-test-cookie": user_token}

    # Create public, private, and unlisted decks
    await async_client.post(
        "/api/v1/decks",
        json={"name": "Public Deck", "privacy": "public"},
        headers=headers,
    )
    await async_client.post(
        "/api/v1/decks",
        json={"name": "Private Deck", "privacy": "private"},
        headers=headers,
    )
    await async_client.post(
        "/api/v1/decks",
        json={"name": "Unlisted Deck", "privacy": "unlisted"},
        headers=headers,
    )

    # Create public, private, and unlisted folders
    await async_client.post(
        "/api/v1/folders",
        json={"name": "Public Folder", "privacy": "public"},
        headers=headers,
    )
    await async_client.post(
        "/api/v1/folders",
        json={"name": "Private Folder", "privacy": "private"},
        headers=headers,
    )
    await async_client.post(
        "/api/v1/folders",
        json={"name": "Unlisted Folder", "privacy": "unlisted"},
        headers=headers,
    )

    response = await async_client.get("/api/v1/community")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    names = {item["name"] for item in data["items"]}
    assert names == {"Public Deck", "Public Folder"}


@pytest.mark.asyncio
async def test_community_pagination(async_client: AsyncClient, user_token: str):
    headers = {"x-test-cookie": user_token}

    for i in range(15):
        await async_client.post(
            "/api/v1/decks",
            json={"name": f"Community Deck {i:02d}", "privacy": "public"},
            headers=headers,
        )

    # Page 1
    res1 = await async_client.get("/api/v1/community?page=1&limit=5")
    assert res1.status_code == 200
    data1 = res1.json()
    assert len(data1["items"]) == 5
    assert data1["total"] == 15
    assert data1["total_pages"] == 3
    assert data1["has_more"] is True

    # Page 2
    res2 = await async_client.get("/api/v1/community?page=2&limit=5")
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2["items"]) == 5

    # Page 3
    res3 = await async_client.get("/api/v1/community?page=3&limit=5")
    assert res3.status_code == 200
    data3 = res3.json()
    assert len(data3["items"]) == 5
    assert data3["has_more"] is False

    # Check that items across pages are distinct
    ids1 = {it["id"] for it in data1["items"]}
    ids2 = {it["id"] for it in data2["items"]}
    ids3 = {it["id"] for it in data3["items"]}
    assert len(ids1.intersection(ids2)) == 0
    assert len(ids2.intersection(ids3)) == 0


@pytest.mark.asyncio
async def test_community_item_type_filter(async_client: AsyncClient, user_token: str):
    headers = {"x-test-cookie": user_token}

    await async_client.post(
        "/api/v1/decks",
        json={"name": "Deck Item", "privacy": "public"},
        headers=headers,
    )
    await async_client.post(
        "/api/v1/folders",
        json={"name": "Folder Item", "privacy": "public"},
        headers=headers,
    )

    # Decks only
    res_decks = await async_client.get("/api/v1/community?item_type=deck")
    assert res_decks.status_code == 200
    data_decks = res_decks.json()
    assert data_decks["total"] == 1
    assert data_decks["items"][0]["type"] == "deck"

    # Folders only
    res_folders = await async_client.get("/api/v1/community?item_type=folder")
    assert res_folders.status_code == 200
    data_folders = res_folders.json()
    assert data_folders["total"] == 1
    assert data_folders["items"][0]["type"] == "folder"

    # All
    res_all = await async_client.get("/api/v1/community?item_type=all")
    assert res_all.status_code == 200
    assert res_all.json()["total"] == 2


@pytest.mark.asyncio
async def test_cannot_star_own_deck_or_folder(
    async_client: AsyncClient, user_token: str
):
    headers = {"x-test-cookie": user_token}

    d_res = await async_client.post(
        "/api/v1/decks",
        json={"name": "My Own Deck", "privacy": "public"},
        headers=headers,
    )
    deck_id = d_res.json()["id"]

    f_res = await async_client.post(
        "/api/v1/folders",
        json={"name": "My Own Folder", "privacy": "public"},
        headers=headers,
    )
    folder_id = f_res.json()["id"]

    # Star own deck fails with 400
    star_d = await async_client.post(f"/api/v1/decks/{deck_id}/star", headers=headers)
    assert star_d.status_code == 400
    assert "Cannot star your own deck" in star_d.json()["detail"]

    # Star own folder fails with 400
    star_f = await async_client.post(
        f"/api/v1/folders/{folder_id}/star", headers=headers
    )
    assert star_f.status_code == 400
    assert "Cannot star your own folder" in star_f.json()["detail"]


@pytest.mark.asyncio
async def test_starring_and_popularity_sort(
    async_client: AsyncClient, user_token: str, guest_token: str
):
    author_headers = {"x-test-cookie": user_token}
    fan_headers = {"x-test-cookie": guest_token}

    d1_res = await async_client.post(
        "/api/v1/decks",
        json={"name": "Deck Alpha (0 stars)", "privacy": "public"},
        headers=author_headers,
    )
    d1_id = d1_res.json()["id"]

    d2_res = await async_client.post(
        "/api/v1/decks",
        json={"name": "Deck Beta (1 star)", "privacy": "public"},
        headers=author_headers,
    )
    d2_id = d2_res.json()["id"]

    f1_res = await async_client.post(
        "/api/v1/folders",
        json={"name": "Folder Gamma (1 star)", "privacy": "public"},
        headers=author_headers,
    )
    f1_id = f1_res.json()["id"]

    # Fan user stars d2 and f1
    star_res = await async_client.post(
        f"/api/v1/decks/{d2_id}/star", headers=fan_headers
    )
    assert star_res.status_code == 200
    assert star_res.json() == {"starred": True, "stars_count": 1}

    star_f_res = await async_client.post(
        f"/api/v1/folders/{f1_id}/star", headers=fan_headers
    )
    assert star_f_res.status_code == 200
    assert star_f_res.json() == {"starred": True, "stars_count": 1}

    # Query sorted by popular
    com_res = await async_client.get(
        "/api/v1/community?sort=popular", headers=fan_headers
    )
    assert com_res.status_code == 200
    items = com_res.json()["items"]
    assert len(items) == 3
    assert items[0]["stars_count"] == 1
    assert items[0]["is_starred"] is True

    # Check user starred endpoint
    starred_res = await async_client.get(
        "/api/v1/community/starred", headers=fan_headers
    )
    assert starred_res.status_code == 200
    starred_data = starred_res.json()
    assert d2_id in starred_data["deck_ids"]
    assert f1_id in starred_data["folder_ids"]

    # Unstar d2
    unstar_res = await async_client.delete(
        f"/api/v1/decks/{d2_id}/star", headers=fan_headers
    )
    assert unstar_res.status_code == 200
    assert unstar_res.json() == {"starred": False, "stars_count": 0}

    # Unstar f1
    unstar_f_res = await async_client.delete(
        f"/api/v1/folders/{f1_id}/star", headers=fan_headers
    )
    assert unstar_f_res.status_code == 200
    assert unstar_f_res.json() == {"starred": False, "stars_count": 0}


@pytest.mark.asyncio
async def test_community_fuzzy_search(async_client: AsyncClient, user_token: str):
    headers = {"x-test-cookie": user_token}

    await async_client.post(
        "/api/v1/decks",
        json={
            "name": "Advanced Japanese Kanji",
            "privacy": "public",
            "properties": {"description": "N1 and N2 kanji vocabulary list"},
        },
        headers=headers,
    )
    await async_client.post(
        "/api/v1/decks",
        json={
            "name": "Organic Chemistry Basics",
            "privacy": "public",
            "properties": {"description": "Alkanes, alkenes and functional groups"},
        },
        headers=headers,
    )
    await async_client.post(
        "/api/v1/folders",
        json={
            "name": "Medical Terminology",
            "privacy": "public",
            "properties": {"description": "Anatomy and clinical terms"},
        },
        headers=headers,
    )

    # Exact search
    res1 = await async_client.get("/api/v1/community?q=Japanese")
    assert res1.status_code == 200
    assert res1.json()["total"] == 1
    assert res1.json()["items"][0]["name"] == "Advanced Japanese Kanji"

    # Fuzzy typo search in deck name (e.g. "kanjii" or "japanse")
    res2 = await async_client.get("/api/v1/community?q=japanse")
    assert res2.status_code == 200
    assert res2.json()["total"] == 1
    assert res2.json()["items"][0]["name"] == "Advanced Japanese Kanji"

    # Description search (single word exact)
    res3 = await async_client.get("/api/v1/community?q=alkanes")
    assert res3.status_code == 200
    assert res3.json()["total"] == 1
    assert res3.json()["items"][0]["name"] == "Organic Chemistry Basics"

    # Description search with typo (e.g. "alkane", "anatomi", "vocabulari")
    res_desc_typo1 = await async_client.get("/api/v1/community?q=anatomi")
    assert res_desc_typo1.status_code == 200
    assert res_desc_typo1.json()["total"] == 1
    assert res_desc_typo1.json()["items"][0]["name"] == "Medical Terminology"

    res_desc_typo2 = await async_client.get("/api/v1/community?q=vocabulari")
    assert res_desc_typo2.status_code == 200
    assert res_desc_typo2.json()["total"] == 1
    assert res_desc_typo2.json()["items"][0]["name"] == "Advanced Japanese Kanji"

    # Description multi-word search (exact and fuzzy)
    res_desc_multi = await async_client.get("/api/v1/community?q=functional groups")
    assert res_desc_multi.status_code == 200
    assert res_desc_multi.json()["total"] == 1
    assert res_desc_multi.json()["items"][0]["name"] == "Organic Chemistry Basics"

    res_desc_multi_fuzzy = await async_client.get("/api/v1/community?q=functionl grups")
    assert res_desc_multi_fuzzy.status_code == 200
    assert res_desc_multi_fuzzy.json()["total"] == 1
    assert res_desc_multi_fuzzy.json()["items"][0]["name"] == "Organic Chemistry Basics"

    # Creator username / display name search (exact and fuzzy)
    res_author_exact = await async_client.get("/api/v1/community?q=normaluser")
    assert res_author_exact.status_code == 200
    assert res_author_exact.json()["total"] >= 3

    res_author_fuzzy = await async_client.get("/api/v1/community?q=normalusr")
    assert res_author_fuzzy.status_code == 200
    assert res_author_fuzzy.json()["total"] >= 3

    # Cross-field search (creator name + deck name or description)
    res_cross1 = await async_client.get("/api/v1/community?q=normaluser kanji")
    assert res_cross1.status_code == 200
    assert res_cross1.json()["total"] == 1
    assert res_cross1.json()["items"][0]["name"] == "Advanced Japanese Kanji"

    res_cross2 = await async_client.get("/api/v1/community?q=normaluser alkanes")
    assert res_cross2.status_code == 200
    assert res_cross2.json()["total"] == 1
    assert res_cross2.json()["items"][0]["name"] == "Organic Chemistry Basics"

    # Folder search
    res4 = await async_client.get("/api/v1/community?q=Medical")
    assert res4.status_code == 200
    assert res4.json()["total"] == 1
    assert res4.json()["items"][0]["name"] == "Medical Terminology"

    # Folder description search
    res_folder_desc = await async_client.get("/api/v1/community?q=clinical terms")
    assert res_folder_desc.status_code == 200
    assert res_folder_desc.json()["total"] == 1
    assert res_folder_desc.json()["items"][0]["name"] == "Medical Terminology"

    # Non-matching search
    res5 = await async_client.get("/api/v1/community?q=xyz987completelyunrelated")
    assert res5.status_code == 200
    assert res5.json()["total"] == 0


@pytest.mark.asyncio
async def test_cascade_delete_deck_and_folder_stars(
    async_client: AsyncClient, user_token: str, guest_token: str
):
    author_headers = {"x-test-cookie": user_token}
    fan_headers = {"x-test-cookie": guest_token}

    d_res = await async_client.post(
        "/api/v1/decks",
        json={"name": "Temporary Deck", "privacy": "public"},
        headers=author_headers,
    )
    deck_id = d_res.json()["id"]

    await async_client.post(f"/api/v1/decks/{deck_id}/star", headers=fan_headers)

    # Delete deck as author
    del_res = await async_client.delete(
        f"/api/v1/decks/{deck_id}", headers=author_headers
    )
    assert del_res.status_code == 204

    # Community listing shouldn't contain the deleted deck
    com_res = await async_client.get("/api/v1/community")
    assert all(it["id"] != deck_id for it in com_res.json()["items"])


@pytest.mark.asyncio
async def test_get_user_favorites(
    async_client: AsyncClient, user_token: str, guest_token: str
):
    author_headers = {"x-test-cookie": user_token}
    fan_headers = {"x-test-cookie": guest_token}

    d_res = await async_client.post(
        "/api/v1/decks",
        json={"name": "Starred Deck", "privacy": "public"},
        headers=author_headers,
    )
    deck_id = d_res.json()["id"]

    f_res = await async_client.post(
        "/api/v1/folders",
        json={"name": "Starred Folder", "privacy": "public"},
        headers=author_headers,
    )
    folder_id = f_res.json()["id"]

    await async_client.post(f"/api/v1/decks/{deck_id}/star", headers=fan_headers)
    await async_client.post(f"/api/v1/folders/{folder_id}/star", headers=fan_headers)

    fav_res = await async_client.get("/api/v1/community/favorites", headers=fan_headers)
    assert fav_res.status_code == 200
    favorites = fav_res.json()
    assert len(favorites) == 2
    fav_ids = {it["id"] for it in favorites}
    assert deck_id in fav_ids
    assert folder_id in fav_ids
    assert all(it["is_starred"] is True for it in favorites)
