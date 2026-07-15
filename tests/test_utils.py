import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models import Deck
from src.utils import generate_unique_slug


@pytest.mark.asyncio
async def test_generate_unique_slug_exceeds_max_length():
    # Mock db session
    db = AsyncMock()

    # We want to simulate a scenario where adding a counter pushes the slug over max_length.
    # We'll set max_length=12.
    # base_slug will be truncated to max(8, 12-10) = 8 characters.
    # Suppose name is "abcdefghij". base_slug will be "abcdefgh".
    # Existing slugs will contain "abcdefgh", "abcdefgh-1", "abcdefgh-2", ..., "abcdefgh-999"
    # "abcdefgh-99" is 11 chars. "abcdefgh-999" is 12 chars.
    # "abcdefgh-1000" is 13 chars (exceeds max_length 12).

    existing = {"abcdefgh"}
    for i in range(1, 1001):
        existing.add(f"abcdefgh-{i}")

    # Mock the execute result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = list(existing)
    db.execute.return_value = mock_result

    user_id = uuid.uuid4()

    with pytest.raises(
        ValueError, match="Cannot generate a unique slug within the 12 character limit."
    ):
        await generate_unique_slug(db, Deck, str(user_id), "abcdefghij", max_length=12)
