import re
import uuid
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from fastapi_users import schemas
from fastapi_users_db_sqlmodel import SQLModelBaseOAuthAccount, SQLModelBaseUserDB
from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField
from pydantic import field_validator, model_validator
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

# --- Card Element Types ---


class TextElement(BaseModel):
    type: Literal["text"]
    content: str


CardElement = Union[TextElement]


# --- OAuth Account ---


class OAuthAccount(SQLModelBaseOAuthAccount, table=True):
    user: "User" = Relationship(back_populates="oauth_accounts")


# --- User Profile Properties ---

ALLOWED_SOCIAL_PLATFORMS = {
    "instagram",
    "facebook",
    "twitter",
    "linkedin",
    "youtube",
    "tiktok",
    "github",
    "website",
}


class SocialLinks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instagram: Optional[str] = None
    facebook: Optional[str] = None
    twitter: Optional[str] = None
    linkedin: Optional[str] = None
    youtube: Optional[str] = None
    tiktok: Optional[str] = None
    github: Optional[str] = None
    website: Optional[str] = None

    @model_validator(mode="after")
    def validate_urls(self) -> "SocialLinks":
        url_pattern = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
        for platform in ALLOWED_SOCIAL_PLATFORMS:
            value = getattr(self, platform)
            if value is not None and not url_pattern.match(value):
                raise ValueError(f"Invalid URL for {platform}: {value}")
        return self


class UserProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bio: Optional[str] = None
    social_links: Optional[SocialLinks] = None

    @field_validator("bio")
    @classmethod
    def validate_bio(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 500:
            raise ValueError("Bio must be 500 characters or fewer")
        return v


# --- User DB Model ---


class User(SQLModelBaseUserDB, table=True):
    __tablename__ = "user"

    is_guest: bool = Field(default=False)
    email_verification_token: Optional[str] = Field(
        default=None, index=True, unique=True
    )
    username: str = Field(unique=True, index=True, max_length=32)
    display_name: str = Field(max_length=80)
    avatar_url: Optional[str] = Field(default=None)
    properties: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    oauth_accounts: List[OAuthAccount] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"lazy": "joined", "cascade": "all, delete-orphan"},
    )
    decks: List["Deck"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
        back_populates="owner",
    )
    folders: List["Folder"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
        back_populates="owner",
    )


# --- User Schemas (Pydantic, not table models) ---


class UserRead(schemas.BaseUser[uuid.UUID]):
    is_guest: bool
    username: str
    display_name: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    social_links: Optional[Dict[str, str]] = None


class UserCreate(schemas.BaseUserCreate):
    is_guest: bool = False
    username: Optional[str] = None
    display_name: Optional[str] = None


class UserUpdate(schemas.BaseUserUpdate):
    username: Optional[str] = PydanticField(
        default=None, min_length=8, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    display_name: Optional[str] = PydanticField(
        default=None, min_length=1, max_length=80
    )
    avatar_url: Optional[str] = None
    bio: Optional[str] = PydanticField(default=None, max_length=500)
    social_links: Optional[SocialLinks] = None


# --- Enums ---


class PrivacyLevel(str, Enum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class ItemProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")
    color: Optional[str] = None


# --- Folder Models ---


class FolderBase(SQLModel):
    name: str = Field(max_length=80)
    slug: str = Field(index=True, max_length=80)
    privacy: PrivacyLevel = Field(default=PrivacyLevel.PRIVATE)
    parent_id: Optional[uuid.UUID] = Field(default=None, foreign_key="folders.id")
    properties: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid slug")
        return v


class FolderCreate(FolderBase):
    properties: Optional[ItemProperties] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    slug: Optional[str] = Field(default=None, max_length=80)
    privacy: Optional[PrivacyLevel] = None
    parent_id: Optional[uuid.UUID] = None
    properties: Optional[ItemProperties] = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid slug")
        return v


class FolderRead(FolderBase):
    id: uuid.UUID
    user_id: uuid.UUID
    properties: Optional[ItemProperties] = None
    type: Literal["folder"]


class Folder(FolderBase, table=True):
    __tablename__ = "folders"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_folder_user_slug"),)

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="user.id")

    owner: Optional["User"] = Relationship(back_populates="folders")
    decks: List["Deck"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
        back_populates="folder",
    )

    parent: Optional["Folder"] = Relationship(
        back_populates="child_folders",
        sa_relationship_kwargs={"remote_side": "Folder.id"},
    )
    child_folders: List["Folder"] = Relationship(
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
    folder_id: Optional[uuid.UUID] = Field(default=None, foreign_key="folders.id")
    properties: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid slug")
        return v


class DeckCreate(DeckBase):
    properties: Optional[ItemProperties] = None


class DeckUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    slug: Optional[str] = Field(default=None, max_length=80)
    privacy: Optional[PrivacyLevel] = None
    folder_id: Optional[uuid.UUID] = None
    properties: Optional[ItemProperties] = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid slug")
        return v


class DeckRead(DeckBase):
    id: uuid.UUID
    user_id: uuid.UUID
    folder_id: Optional[uuid.UUID] = None
    properties: Optional[ItemProperties] = None
    type: Literal["deck"]


class Deck(DeckBase, table=True):
    __tablename__ = "decks"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_deck_user_slug"),)

    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: Optional[uuid.UUID] = Field(default=None, foreign_key="user.id")

    owner: Optional["User"] = Relationship(back_populates="decks")
    folder: Optional["Folder"] = Relationship(back_populates="decks")
    cards: List["Card"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin", "cascade": "all, delete-orphan"},
        back_populates="deck",
    )

    @property
    def type(self) -> str:
        return "deck"


# --- Card Models ---


class CardBase(SQLModel):
    front: List[CardElement] = Field(sa_column=Column(JSON))
    back: List[CardElement] = Field(sa_column=Column(JSON))
    order: int = Field(default=0)


class CardCreate(CardBase):
    pass


class CardUpdate(BaseModel):
    front: Optional[List[CardElement]] = None
    back: Optional[List[CardElement]] = None


class CardReorder(BaseModel):
    card_ids: List[uuid.UUID]


class CardRead(CardBase):
    id: uuid.UUID
    deck_id: uuid.UUID


class Card(CardBase, table=True):
    __tablename__ = "cards"
    id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4, primary_key=True)
    deck_id: Optional[uuid.UUID] = Field(default=None, foreign_key="decks.id")

    deck: Optional[Deck] = Relationship(back_populates="cards")


class FolderWithContents(FolderRead):
    folders: List[FolderRead] = []
    decks: List[DeckRead] = []
