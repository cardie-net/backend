import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import field_validator
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    TypeDecorator,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.orm import column_property
from sqlmodel import Field, Relationship, SQLModel

from .common import (
    MAX_CARD_TEXT_LENGTH,
    MAX_NAME_LENGTH,
    MAX_URL_LENGTH,
    PrivacyLevel,
    validate_slug,
)


class UTCDateTime(TypeDecorator):
    """DateTime type that guarantees timezone-aware UTC datetime values."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


# --- Card Element Types ---


class TextElement(SQLModel):
    type: Literal["text"]
    content: str = Field(max_length=MAX_CARD_TEXT_LENGTH)


class ImageElement(SQLModel):
    type: Literal["image"]
    url: str = Field(max_length=MAX_URL_LENGTH)


CardElement = Annotated[Union[TextElement, ImageElement], Field(discriminator="type")]


# --- OAuth Account ---


class OAuthAccount(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    oauth_name: str = Field(index=True)
    access_token: str
    expires_at: int | None = None
    refresh_token: str | None = None
    account_id: str = Field(index=True)
    account_email: str
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    user: "User" = Relationship(back_populates="oauth_accounts")


# --- Pending Registration ---


class PendingRegistration(SQLModel, table=True):
    """Credentials staged for a guest account until the email is verified.

    Signing up never mutates the guest user row: credentials live here and
    the account is promoted in place only after email verification.
    """

    __tablename__ = "pending_registrations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    username: str | None = Field(default=None, max_length=32)
    display_name: str | None = Field(default=None, max_length=80)
    email_verification_token: str = Field(index=True, unique=True)
    guest_user_id: uuid.UUID = Field(
        foreign_key="user.id", index=True, ondelete="CASCADE"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            UTCDateTime,
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
        ),
    )


# --- User DB Model ---


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    is_guest: bool = Field(default=False)
    email_verification_token: str | None = Field(default=None, index=True, unique=True)
    reset_password_token: str | None = Field(default=None, index=True, unique=True)
    username: str = Field(unique=True, index=True, max_length=32)
    display_name: str = Field(max_length=80)
    avatar_url: str | None = Field(default=None)
    properties: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            UTCDateTime,
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
        ),
    )
    last_active_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            UTCDateTime,
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
        ),
    )

    oauth_accounts: list["OAuthAccount"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={
            "lazy": "joined",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
    )
    decks: list["Deck"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="owner",
    )
    folders: list["Folder"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="owner",
    )
    starred_decks: list["DeckStar"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="user",
    )
    starred_folders: list["FolderStar"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="user",
    )
    card_progress: list["CardProgress"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="user",
    )
    srs_card_progress: list["SRSCardProgress"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="user",
    )
    srs_deck_activations: list["SRSDeckActivation"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="user",
    )
    deck_match_times: list["DeckMatchTime"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="user",
    )
    deck_exam_scores: list["DeckExamScore"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="user",
    )
    daily_activities: list["UserDailyActivity"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="user",
    )


# --- Star Models ---


class DeckStar(SQLModel, table=True):
    __tablename__ = "deck_stars"
    __table_args__ = (UniqueConstraint("user_id", "deck_id", name="uq_user_deck_star"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    deck_id: uuid.UUID = Field(foreign_key="decks.id", index=True, ondelete="CASCADE")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            UTCDateTime,
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
        ),
    )

    user: Optional["User"] = Relationship(back_populates="starred_decks")
    deck: Optional["Deck"] = Relationship(back_populates="stars")


class FolderStar(SQLModel, table=True):
    __tablename__ = "folder_stars"
    __table_args__ = (
        UniqueConstraint("user_id", "folder_id", name="uq_user_folder_star"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    folder_id: uuid.UUID = Field(
        foreign_key="folders.id", index=True, ondelete="CASCADE"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            UTCDateTime,
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
        ),
    )

    user: Optional["User"] = Relationship(back_populates="starred_folders")
    folder: Optional["Folder"] = Relationship(back_populates="stars")


# --- Folder Models ---


class FolderBase(SQLModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    slug: str = Field(index=True, max_length=80)
    privacy: PrivacyLevel = Field(default=PrivacyLevel.PRIVATE)
    parent_id: uuid.UUID | None = Field(
        default=None, foreign_key="folders.id", ondelete="CASCADE"
    )
    properties: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    @field_validator("name")
    @classmethod
    def validate_name_field(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty or whitespace only")
        if len(v) > MAX_NAME_LENGTH:
            raise ValueError(f"Name cannot exceed {MAX_NAME_LENGTH} characters")
        return v

    @field_validator("slug")
    @classmethod
    def validate_slug_field(cls, v: str) -> str:
        return validate_slug(v)


class Folder(FolderBase, table=True):
    __tablename__ = "folders"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_folder_user_slug"),)

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", ondelete="CASCADE"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            UTCDateTime,
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            UTCDateTime,
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
        ),
    )

    owner: Optional["User"] = Relationship(back_populates="folders")
    decks: list["Deck"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="folder",
    )
    stars: list["FolderStar"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="folder",
    )

    parent: Optional["Folder"] = Relationship(
        back_populates="child_folders",
        sa_relationship_kwargs={"remote_side": "Folder.id"},
    )
    child_folders: list["Folder"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
    )

    @property
    def type(self) -> str:
        return "folder"


# --- Card Models ---


class CardBase(SQLModel):
    front: list[CardElement] = Field(sa_column=Column(JSON))
    back: list[CardElement] = Field(sa_column=Column(JSON))
    order: int = Field(default=0)

    @field_validator("front", "back")
    @classmethod
    def validate_card_side(cls, elements: list[Any]) -> list[Any]:
        if not isinstance(elements, list):
            return elements
        total_text_length = sum(
            (
                len(el.content)
                if isinstance(el, TextElement)
                else (
                    len(el.get("content", ""))
                    if isinstance(el, dict) and el.get("type") == "text"
                    else 0
                )
            )
            for el in elements
        )
        if total_text_length > MAX_CARD_TEXT_LENGTH:
            raise ValueError(
                f"Card side text cannot exceed {MAX_CARD_TEXT_LENGTH} characters"
            )
        image_count = sum(
            1
            for el in elements
            if isinstance(el, ImageElement)
            or (isinstance(el, dict) and el.get("type") == "image")
        )
        if image_count > 1:
            raise ValueError("Card side cannot have more than 1 image")
        return elements


class Card(CardBase, table=True):
    __tablename__ = "cards"
    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    deck_id: uuid.UUID | None = Field(
        default=None, foreign_key="decks.id", ondelete="CASCADE"
    )

    deck: Optional["Deck"] = Relationship(back_populates="cards")
    progress: list["CardProgress"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="card",
    )
    srs_progress: list["SRSCardProgress"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="card",
    )


# --- Deck Models ---


class DeckBase(SQLModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    slug: str = Field(index=True, max_length=80)
    privacy: PrivacyLevel = Field(default=PrivacyLevel.PRIVATE)
    folder_id: uuid.UUID | None = Field(
        default=None, foreign_key="folders.id", ondelete="CASCADE"
    )
    properties: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    @field_validator("name")
    @classmethod
    def validate_name_field(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty or whitespace only")
        if len(v) > MAX_NAME_LENGTH:
            raise ValueError(f"Name cannot exceed {MAX_NAME_LENGTH} characters")
        return v

    @field_validator("slug")
    @classmethod
    def validate_slug_field(cls, v: str) -> str:
        return validate_slug(v)


class Deck(DeckBase, table=True):
    __tablename__ = "decks"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_deck_user_slug"),)

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", ondelete="CASCADE"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            UTCDateTime,
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
        ),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            UTCDateTime,
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
        ),
    )

    owner: Optional["User"] = Relationship(back_populates="decks")
    folder: Optional["Folder"] = Relationship(back_populates="decks")
    cards: list["Card"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="deck",
    )
    stars: list["DeckStar"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="deck",
    )
    srs_activations: list["SRSDeckActivation"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="deck",
    )
    match_times: list["DeckMatchTime"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="deck",
    )
    exam_scores: list["DeckExamScore"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
        back_populates="deck",
    )

    @property
    def type(self) -> str:
        return "deck"


# --- Learning Progress Models ---


class CardProgress(SQLModel, table=True):
    __tablename__ = "card_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", name="uq_user_card_progress"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    card_id: uuid.UUID = Field(foreign_key="cards.id", index=True, ondelete="CASCADE")
    box: int = Field(default=1)  # 1, 2, or 3

    card: Optional["Card"] = Relationship(back_populates="progress")
    user: Optional["User"] = Relationship(back_populates="card_progress")


class SRSCardProgress(SQLModel, table=True):
    __tablename__ = "srs_card_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", name="uq_user_card_srs_progress"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    card_id: uuid.UUID = Field(foreign_key="cards.id", index=True, ondelete="CASCADE")
    repetitions: int = Field(default=0)
    ease_factor: float = Field(default=2.5)
    interval: float = Field(default=0.0)
    due_date: str | None = Field(default=None)
    last_reviewed: str | None = Field(default=None)

    card: Optional["Card"] = Relationship(back_populates="srs_progress")
    user: Optional["User"] = Relationship(back_populates="srs_card_progress")


class SRSDeckActivation(SQLModel, table=True):
    __tablename__ = "srs_deck_activations"
    __table_args__ = (
        UniqueConstraint("user_id", "deck_id", name="uq_user_deck_srs_activation"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    deck_id: uuid.UUID = Field(foreign_key="decks.id", index=True, ondelete="CASCADE")
    activated_at: str | None = Field(default=None)

    deck: Optional["Deck"] = Relationship(back_populates="srs_activations")
    user: Optional["User"] = Relationship(back_populates="srs_deck_activations")


Deck.cards_count = column_property(
    select(func.count(Card.id))
    .where(Card.deck_id == Deck.id)
    .correlate_except(Card)
    .scalar_subquery()
)

Deck.stars_count = column_property(
    select(func.count(DeckStar.id))
    .where(DeckStar.deck_id == Deck.id)
    .correlate_except(DeckStar)
    .scalar_subquery()
)

Folder.stars_count = column_property(
    select(func.count(FolderStar.id))
    .where(FolderStar.folder_id == Folder.id)
    .correlate_except(FolderStar)
    .scalar_subquery()
)

Folder.decks_count = column_property(
    select(func.count(Deck.id))
    .where(Deck.folder_id == Folder.id)
    .correlate_except(Deck)
    .scalar_subquery()
)


class DeckMatchTime(SQLModel, table=True):
    __tablename__ = "deck_match_times"
    __table_args__ = (
        UniqueConstraint("user_id", "deck_id", name="uq_user_deck_match_time"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    deck_id: uuid.UUID = Field(foreign_key="decks.id", index=True, ondelete="CASCADE")
    best_time_ms: int

    deck: Optional["Deck"] = Relationship(back_populates="match_times")
    user: Optional["User"] = Relationship(back_populates="deck_match_times")


class DeckExamScore(SQLModel, table=True):
    __tablename__ = "deck_exam_scores"
    __table_args__ = (
        UniqueConstraint("user_id", "deck_id", name="uq_user_deck_exam_score"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    deck_id: uuid.UUID = Field(foreign_key="decks.id", index=True, ondelete="CASCADE")
    best_score_percentage: int

    deck: Optional["Deck"] = Relationship(back_populates="exam_scores")
    user: Optional["User"] = Relationship(back_populates="deck_exam_scores")


class UserDailyActivity(SQLModel, table=True):
    __tablename__ = "user_daily_activity"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_user_daily_activity"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    date: str = Field(index=True)  # Format: YYYY-MM-DD
    points: int = Field(default=0)
    activities_count: int = Field(default=0)
    details: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    user: Optional["User"] = Relationship(back_populates="daily_activities")
