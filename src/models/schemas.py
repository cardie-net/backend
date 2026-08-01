import uuid
from typing import Any, Literal

from pydantic import BaseModel
from pydantic import Field as PydanticField
from pydantic import field_validator
from sqlmodel import Field

from .common import (
    ItemProperties,
    PrivacyLevel,
    SocialLinks,
    validate_optional_slug,
    validate_slug,
)
from .tables import CardBase, CardElement, DeckBase, FolderBase

# --- User Schemas ---


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    is_guest: bool
    username: str
    display_name: str
    avatar_url: str | None = None
    bio: str | None = None
    social_links: dict[str, str] | None = None


class UserCreate(BaseModel):
    email: str
    password: str
    is_guest: bool = False
    username: str | None = None
    display_name: str | None = None


class UserUpdate(BaseModel):
    password: str | None = None
    username: str | None = PydanticField(
        default=None, min_length=8, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    display_name: str | None = PydanticField(default=None, min_length=1, max_length=80)
    avatar_url: str | None = None
    bio: str | None = PydanticField(default=None, max_length=500)
    social_links: SocialLinks | None = None


# --- Folder Schemas ---


class FolderCreate(FolderBase):
    slug: str | None = Field(default=None, max_length=80)
    properties: ItemProperties | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug_create(cls, v: str | None) -> str | None:
        return validate_optional_slug(v)


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    slug: str | None = Field(default=None, max_length=80)
    privacy: PrivacyLevel | None = None
    parent_id: uuid.UUID | None = None
    properties: ItemProperties | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        return validate_optional_slug(v)


class FolderRead(FolderBase):
    id: uuid.UUID
    user_id: uuid.UUID
    properties: ItemProperties | None = None
    type: Literal["folder"]


class FolderWithContents(FolderRead):
    folders: list["FolderRead"] = []
    decks: list["DeckRead"] = []


# --- Deck Schemas ---


class DeckCreate(DeckBase):
    slug: str | None = Field(default=None, max_length=80)
    properties: ItemProperties | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug_create(cls, v: str | None) -> str | None:
        return validate_optional_slug(v)


class DeckUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    slug: str | None = Field(default=None, max_length=80)
    privacy: PrivacyLevel | None = None
    folder_id: uuid.UUID | None = None
    properties: ItemProperties | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        return validate_optional_slug(v)


class DeckRead(DeckBase):
    id: uuid.UUID
    user_id: uuid.UUID
    folder_id: uuid.UUID | None = None
    properties: ItemProperties | None = None
    type: Literal["deck"]


# --- Card Schemas ---


class CardCreate(CardBase):
    pass


class CardUpdate(BaseModel):
    front: list[CardElement] | None = None
    back: list[CardElement] | None = None


class CardReorder(BaseModel):
    card_ids: list[uuid.UUID]


class CardRead(CardBase):
    id: uuid.UUID
    deck_id: uuid.UUID


# --- Learning Progress Schemas ---


class CardProgressUpdate(BaseModel):
    card_id: uuid.UUID
    box: int


class CardProgressSyncRequest(BaseModel):
    progress: list[CardProgressUpdate]


class CardProgressRead(BaseModel):
    card_id: uuid.UUID
    box: int


class SRSCardProgressRead(BaseModel):
    card_id: uuid.UUID
    repetitions: int
    ease_factor: float
    interval: float
    due_date: str | None
    last_reviewed: str | None


class SRSReviewItem(BaseModel):
    card_id: uuid.UUID
    rating: int


class SRSReviewRequest(BaseModel):
    reviews: list[SRSReviewItem]


class SRSDeckCounts(BaseModel):
    new_count: int
    learning_count: int
    review_count: int


class SRSStudyResponse(BaseModel):
    new_cards: list[SRSCardProgressRead]
    learning_cards: list[SRSCardProgressRead]
    review_cards: list[SRSCardProgressRead]
