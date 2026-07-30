import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models import Deck
from src.utils import generate_unique_slug


@pytest.mark.asyncio
async def test_generate_unique_slug_happy_path():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result

    user_id = uuid.uuid4()
    slug = await generate_unique_slug(db, Deck, str(user_id), "My Test Deck")

    assert slug == "mytestdeck"


@pytest.mark.asyncio
async def test_generate_unique_slug_with_collision():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = ["mytestdeck", "mytestdeck-1"]
    db.execute.return_value = mock_result

    user_id = uuid.uuid4()
    slug = await generate_unique_slug(db, Deck, str(user_id), "My Test Deck")

    assert slug == "mytestdeck-2"


@pytest.mark.asyncio
async def test_generate_unique_slug_exceeds_max_length():
    # Mock db session
    db = AsyncMock()

    # We want to simulate a scenario where adding a counter pushes the slug over max_length.
    # We'll set max_length=5.
    # base_slug will be truncated to max(1, 5-10) = 1 characters.
    # Suppose name is "abcdefghij". base_slug will be "a".
    # Existing slugs will contain "a", "a-1", "a-2", ..., "a-999"
    # "a-99" is 4 chars. "a-999" is 5 chars.
    # "a-1000" is 6 chars (exceeds max_length 5).

    existing = {"a"}
    for i in range(1, 1001):
        existing.add(f"a-{i}")

    # Mock the execute result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = list(existing)
    db.execute.return_value = mock_result

    user_id = uuid.uuid4()

    with pytest.raises(
        ValueError, match="Cannot generate a unique slug within the 5 character limit."
    ):
        await generate_unique_slug(db, Deck, str(user_id), "abcdefghij", max_length=5)
