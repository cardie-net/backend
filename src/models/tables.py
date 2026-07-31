import uuid
from typing import Any, Literal, Optional

from pydantic import field_validator
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from .common import PrivacyLevel, validate_slug

# --- Card Element Types ---


class TextElement(SQLModel):
    type: Literal["text"]
    content: str


CardElement = TextElement


# --- OAuth Account ---


class OAuthAccount(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    oauth_name: str = Field(index=True)
    access_token: str
    expires_at: int | None = None
    refresh_token: str | None = None
    account_id: str = Field(index=True)
    account_email: str
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    user: "User" = Relationship(back_populates="oauth_accounts")


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

    oauth_accounts: list["OAuthAccount"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "joined", "cascade": "all, delete-orphan"},
    )
    decks: list["Deck"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
        back_populates="owner",
    )
    folders: list["Folder"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
        back_populates="owner",
    )


# --- Folder Models ---


class FolderBase(SQLModel):
    name: str = Field(max_length=80)
    slug: str = Field(index=True, max_length=80)
    privacy: PrivacyLevel = Field(default=PrivacyLevel.PRIVATE)
    parent_id: uuid.UUID | None = Field(default=None, foreign_key="folders.id")
    properties: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    @field_validator("slug")
    @classmethod
    def validate_slug_field(cls, v: str) -> str:
        return validate_slug(v)


class Folder(FolderBase, table=True):
    __tablename__ = "folders"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_folder_user_slug"),)

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID | None = Field(default=None, foreign_key="user.id")

    owner: Optional["User"] = Relationship(back_populates="folders")
    decks: list["Deck"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
        back_populates="folder",
    )

    parent: Optional["Folder"] = Relationship(
        back_populates="child_folders",
        sa_relationship_kwargs={"remote_side": "Folder.id"},
    )
    child_folders: list["Folder"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
    )

    @property
    def type(self) -> str:
        return "folder"


# --- Deck Models ---


class DeckBase(SQLModel):
    name: str = Field(max_length=80)
    slug: str = Field(index=True, max_length=80)
    privacy: PrivacyLevel = Field(default=PrivacyLevel.PRIVATE)
    folder_id: uuid.UUID | None = Field(default=None, foreign_key="folders.id")
    properties: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    @field_validator("slug")
    @classmethod
    def validate_slug_field(cls, v: str) -> str:
        return validate_slug(v)


class Deck(DeckBase, table=True):
    __tablename__ = "decks"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_deck_user_slug"),)

    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID | None = Field(default=None, foreign_key="user.id")

    owner: Optional["User"] = Relationship(back_populates="decks")
    folder: Optional["Folder"] = Relationship(back_populates="decks")
    cards: list["Card"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
        back_populates="deck",
    )

    @property
    def type(self) -> str:
        return "deck"


# --- Card Models ---


class CardBase(SQLModel):
    front: list[CardElement] = Field(sa_column=Column(JSON))
    back: list[CardElement] = Field(sa_column=Column(JSON))
    order: int = Field(default=0)


class Card(CardBase, table=True):
    __tablename__ = "cards"
    id: uuid.UUID | None = Field(default_factory=uuid.uuid4, primary_key=True)
    deck_id: uuid.UUID | None = Field(default=None, foreign_key="decks.id")

    deck: Deck | None = Relationship(back_populates="cards")


# --- Learning Progress Models ---


class CardProgress(SQLModel, table=True):
    __tablename__ = "card_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", name="uq_user_card_progress"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    card_id: uuid.UUID = Field(foreign_key="cards.id", index=True)
    box: int = Field(default=1)  # 1, 2, or 3
