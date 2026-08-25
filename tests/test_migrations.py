import uuid

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import _migrate_legacy_unverified_users
from src.models.tables import PendingRegistration, User


async def _insert_raw_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    email: str,
    username: str,
    *,
    is_guest: bool = False,
    is_verified: bool = False,
) -> None:
    """Insert a user row the way the app does (32-hex id, bcrypt hash)."""
    from src.auth.utils import get_password_hash

    await session.execute(
        insert(User).values(
            id=user_id,
            email=email,
            hashed_password=get_password_hash("oldpassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=is_verified,
            is_guest=is_guest,
            username=username,
            display_name=username,
            email_verification_token="legacytoken1" if not is_verified else None,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_migration_converts_legacy_unverified_user(async_session: AsyncSession):
    user_id = uuid.uuid4()
    await _insert_raw_user(async_session, user_id, "legacy@example.com", "legacyuser")

    await _migrate_legacy_unverified_users(async_session)

    user = await async_session.get(User, user_id)
    assert user is not None  # row kept (data preserved)
    assert user.is_guest is True
    assert user.email.startswith("guest_")
    assert user.email.endswith("@guest.example.com")
    assert user.email != "legacy@example.com"
    assert user.email_verification_token is None

    pendings = (
        (await async_session.execute(select(PendingRegistration))).scalars().all()
    )
    assert len(pendings) == 1
    pending = pendings[0]
    assert pending.email == "legacy@example.com"
    assert pending.guest_user_id == user_id
    assert pending.email_verification_token == "legacytoken1"


@pytest.mark.asyncio
async def test_migration_is_idempotent(async_session: AsyncSession):
    user_id = uuid.uuid4()
    await _insert_raw_user(async_session, user_id, "legacy@example.com", "legacyuser")

    await _migrate_legacy_unverified_users(async_session)
    await _migrate_legacy_unverified_users(async_session)

    count = (
        await async_session.execute(text("SELECT COUNT(*) FROM pending_registrations"))
    ).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_migration_skips_verified_and_guest_users(async_session: AsyncSession):
    real_id = uuid.uuid4()
    guest_id = uuid.uuid4()
    await _insert_raw_user(
        async_session, real_id, "real@example.com", "realuser", is_verified=True
    )
    await _insert_raw_user(
        async_session, guest_id, "guest_x@guest.example.com", "guestx", is_guest=True
    )

    await _migrate_legacy_unverified_users(async_session)

    count = (
        await async_session.execute(text("SELECT COUNT(*) FROM pending_registrations"))
    ).scalar()
    assert count == 0

    real = await async_session.get(User, real_id)
    guest = await async_session.get(User, guest_id)
    assert real.email == "real@example.com"
    assert real.is_guest is False
    assert guest.is_guest is True
