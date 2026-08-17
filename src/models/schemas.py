import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel
from pydantic import Field as PydanticField
from pydantic import field_validator
from sqlmodel import Field

from .common import (
    ItemProperties,
    PrivacyLevel,
    SocialLinks,
    is_reserved_username,
    validate_optional_slug,
    validate_slug,
)
from .tables import CardBase, CardElement, DeckBase, FolderBase

# --- User Schemas ---


class UserPreferences(BaseModel):
    language: str | None = None
    themeConfig: dict[str, Any] | None = None
    learning_multiple_choice: bool | None = None
    overview_shuffle: bool | None = None


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
    preferences: UserPreferences | None = None
    created_at: datetime | None = None
    last_active_at: datetime | None = None


class UserCreate(BaseModel):
    email: str
    password: str
    is_guest: bool = False
    username: str | None = PydanticField(
        default=None, min_length=8, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    display_name: str | None = PydanticField(default=None, min_length=1, max_length=80)

    @field_validator("username")
    @classmethod
    def validate_username_create(cls, v: str | None) -> str | None:
        if v is not None and is_reserved_username(v):
            raise ValueError("Username is reserved")
        return v


class UserUpdate(BaseModel):
    password: str | None = None
    username: str | None = PydanticField(
        default=None, min_length=8, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    display_name: str | None = PydanticField(default=None, min_length=1, max_length=80)
    avatar_url: str | None = None
    bio: str | None = PydanticField(default=None, max_length=500)
    social_links: SocialLinks | None = None
    preferences: UserPreferences | None = None

    @field_validator("username")
    @classmethod
    def validate_username_update(cls, v: str | None) -> str | None:
        if v is not None and is_reserved_username(v):
            raise ValueError("Username is reserved")
        return v


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
    created_at: datetime | None = None
    updated_at: datetime | None = None
    stars_count: int = 0
    decks_count: int = 0
    is_starred: bool = False


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
    cards_count: int = 0
    stars_count: int = 0
    is_starred: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DeckMatchTimeUpdate(BaseModel):
    time_ms: int


class DeckMatchTimeRead(BaseModel):
    best_time_ms: int | None


class DeckExamScoreUpdate(BaseModel):
    score_percentage: int = PydanticField(ge=0, le=100)


class DeckExamScoreRead(BaseModel):
    best_score_percentage: int | None


# --- Card Schemas ---


class CardCreate(CardBase):
    pass


class CardBatchCreate(BaseModel):
    cards: list[CardCreate] = PydanticField(min_length=1, max_length=5000)


class DeckImportRequest(BaseModel):
    name: str = PydanticField(min_length=1, max_length=80)
    slug: str | None = PydanticField(default=None, max_length=80)
    privacy: PrivacyLevel = PrivacyLevel.PRIVATE
    folder_id: uuid.UUID | None = None
    properties: ItemProperties | None = None
    cards: list[CardCreate] = PydanticField(default_factory=list, max_length=5000)

    @field_validator("slug")
    @classmethod
    def validate_slug_import(cls, v: str | None) -> str | None:
        return validate_optional_slug(v)


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
    activated: bool = False
    new_count: int
    learning_count: int
    review_count: int


class SRSStudyResponse(BaseModel):
    new_cards: list[SRSCardProgressRead]
    learning_cards: list[SRSCardProgressRead]
    review_cards: list[SRSCardProgressRead]


# --- User Daily Activity Schemas ---


class UserDailyActivityRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    date: str
    points: int
    activities_count: int
    details: dict[str, Any] | None = None


class UserActivityRecordRequest(BaseModel):
    points: int = PydanticField(gt=0)
    count: int = PydanticField(default=1, ge=1)
    activity_type: str | None = None
    date: str | None = None


class UserActivitySummary(BaseModel):
    activities: list[UserDailyActivityRead]
    total_points: int
    current_streak: int
    longest_streak: int
    total_active_days: int


# --- Community & Star Schemas ---


class ItemOwner(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    avatar_url: str | None = None
    is_guest: bool = False


class CommunityDeckRead(DeckBase):
    id: uuid.UUID
    user_id: uuid.UUID
    folder_id: uuid.UUID | None = None
    properties: ItemProperties | None = None
    type: Literal["deck"] = "deck"
    cards_count: int = 0
    stars_count: int = 0
    is_starred: bool = False
    created_at: datetime
    updated_at: datetime
    owner: ItemOwner


class CommunityFolderRead(FolderBase):
    id: uuid.UUID
    user_id: uuid.UUID
    properties: ItemProperties | None = None
    type: Literal["folder"] = "folder"
    decks_count: int = 0
    stars_count: int = 0
    is_starred: bool = False
    created_at: datetime
    updated_at: datetime
    owner: ItemOwner


CommunityItem = Annotated[
    CommunityDeckRead | CommunityFolderRead, PydanticField(discriminator="type")
]


class CommunityResponse(BaseModel):
    items: list[CommunityItem]
    total: int
    page: int
    limit: int
    total_pages: int
    has_more: bool


class StarResponse(BaseModel):
    starred: bool
    stars_count: int


class UserStarredResponse(BaseModel):
    deck_ids: list[uuid.UUID]
    folder_ids: list[uuid.UUID]
