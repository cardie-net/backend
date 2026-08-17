from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from src.config import settings

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


async def create_db_and_tables() -> None:
    """Create all configured database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        if conn.dialect.name == "postgresql":
            await _ensure_postgres_foreign_key_cascades(conn)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session for a request."""
    async with async_session_maker() as session:
        yield session
