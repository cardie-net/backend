import uuid
from typing import AsyncGenerator

from sqlalchemy import event, insert, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from src.config import settings
from src.models.tables import Deck, Folder, PendingRegistration, PrivacyLevel, User

DATABASE_URL = settings.DATABASE_URL
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_async_engine(DATABASE_URL, connect_args=connect_args)
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


CASCADE_FOREIGN_KEYS = [
    ("card_progress", "card_id", "cards", "id"),
    ("card_progress", "user_id", "user", "id"),
    ("srs_card_progress", "card_id", "cards", "id"),
    ("srs_card_progress", "user_id", "user", "id"),
    ("srs_deck_activations", "deck_id", "decks", "id"),
    ("srs_deck_activations", "user_id", "user", "id"),
    ("deck_match_times", "deck_id", "decks", "id"),
    ("deck_match_times", "user_id", "user", "id"),
    ("deck_exam_scores", "deck_id", "decks", "id"),
    ("deck_exam_scores", "user_id", "user", "id"),
    ("deck_stars", "deck_id", "decks", "id"),
    ("deck_stars", "user_id", "user", "id"),
    ("folder_stars", "folder_id", "folders", "id"),
    ("folder_stars", "user_id", "user", "id"),
    ("cards", "deck_id", "decks", "id"),
    ("decks", "user_id", "user", "id"),
    ("decks", "folder_id", "folders", "id"),
    ("folders", "user_id", "user", "id"),
    ("folders", "parent_id", "folders", "id"),
    ("user_daily_activity", "user_id", "user", "id"),
    ("oauthaccount", "user_id", "user", "id"),
]


async def _ensure_postgres_foreign_key_cascades(conn) -> None:
    """Ensure PostgreSQL foreign key constraints have ON DELETE CASCADE."""
    for child_tbl, child_col, parent_tbl, parent_col in CASCADE_FOREIGN_KEYS:
        table_check = await conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name IN (:t1, :t2)"
            ),
            {"t1": child_tbl, "t2": parent_tbl},
        )
        if (table_check.scalar() or 0) < 2:
            continue

        result = await conn.execute(
            text("""
                SELECT c.conname, c.confdeltype
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey)
                WHERE t.relname = :tbl AND a.attname = :col AND c.contype = 'f';
                """),
            {"tbl": child_tbl, "col": child_col},
        )
        rows = result.all()
        for conname, confdeltype in rows:
            if confdeltype != "c":
                await conn.execute(
                    text(f'ALTER TABLE "{child_tbl}" DROP CONSTRAINT "{conname}"')
                )
                await conn.execute(
                    text(
                        f'ALTER TABLE "{child_tbl}" ADD CONSTRAINT "{conname}" '
                        f'FOREIGN KEY ("{child_col}") REFERENCES "{parent_tbl}"("{parent_col}") '
                        f"ON DELETE CASCADE"
                    )
                )


async def _migrate_legacy_unverified_users(session: AsyncSession) -> None:
    """Move legacy unverified accounts back to guest status.

    Older versions promoted the guest row at signup and left it unverified
    until the email was confirmed. Those rows are converted to the deferred
    model: credentials go into pending_registrations (keeping the original
    verification token so old emailed links still work) and the user row is
    reverted to guest boilerplate. Idempotent: only touches non-guest,
    unverified users, which can no longer be created.
    """
    result = await session.execute(
        select(
            User.id,
            User.email,
            User.hashed_password,
            User.username,
            User.display_name,
            User.email_verification_token,
        ).where(
            User.is_guest == False, User.is_verified == False
        )  # noqa: E712
    )
    legacy_rows = result.all()

    from .auth.utils import get_password_hash  # lazy: avoids circular import

    def _as_uuid(value) -> uuid.UUID:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))

    for row in legacy_rows:
        session.add(
            PendingRegistration(
                email=row.email,
                hashed_password=row.hashed_password,
                username=row.username,
                display_name=row.display_name,
                email_verification_token=row.email_verification_token
                or uuid.uuid4().hex[:10],
                guest_user_id=_as_uuid(row.id),
            )
        )

    for row in legacy_rows:
        guest_id = uuid.uuid4().hex[:20]
        await session.execute(
            update(User)
            .where(User.id == _as_uuid(row.id))
            .values(
                email=f"guest_{guest_id}@guest.example.com",
                hashed_password=get_password_hash(uuid.uuid4().hex),
                is_guest=True,
                email_verification_token=None,
            )
        )
    if legacy_rows:
        await session.commit()


async def _demote_guest_public_items(session: AsyncSession) -> None:
    """Force all decks and folders owned by guest accounts back to private.

    Guests must not be able to share or publish content. Idempotent: only
    touches rows whose privacy is not already private.
    """
    for model in (Deck, Folder):
        await session.execute(
            update(model)
            .where(
                model.user_id.in_(
                    select(User.id).where(User.is_guest == True)
                ),  # noqa: E712
                model.privacy != PrivacyLevel.PRIVATE,
            )
            .values(privacy=PrivacyLevel.PRIVATE)
        )
    await session.commit()


async def create_db_and_tables() -> None:
    """Create all configured database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        if conn.dialect.name == "postgresql":
            await _ensure_postgres_foreign_key_cascades(conn)

    async with async_session_maker() as session:
        await _migrate_legacy_unverified_users(session)
        await _demote_guest_public_items(session)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for a request."""
    async with async_session_maker() as session:
        yield session
