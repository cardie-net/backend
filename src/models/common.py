import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# Compiled regex for slug validation (used across multiple models)
SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
URL_PATTERN = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def validate_slug(value: str) -> str:
    """Validate that a slug contains only URL-safe characters."""
    if not SLUG_PATTERN.match(value):
        raise ValueError("Invalid slug")
    return value


def validate_optional_slug(value: str | None) -> str | None:
    """Validate an optional slug value."""
    if value is None:
        return value
    return validate_slug(value)


class PrivacyLevel(str, Enum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class ItemProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")
    color: str | None = None


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

    instagram: str | None = None
    facebook: str | None = None
    twitter: str | None = None
    linkedin: str | None = None
    youtube: str | None = None
    tiktok: str | None = None
    github: str | None = None
    website: str | None = None

    @model_validator(mode="after")
    def validate_urls(self) -> "SocialLinks":
        for platform in ALLOWED_SOCIAL_PLATFORMS:
            value = getattr(self, platform)
            if value is not None and not URL_PATTERN.match(value):
                raise ValueError(f"Invalid URL for {platform}: {value}")
        return self


class UserProperties(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bio: str | None = None
    social_links: SocialLinks | None = None

    @field_validator("bio")
    @classmethod
    def validate_bio(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 500:
            raise ValueError("Bio must be 500 characters or fewer")
        return v
