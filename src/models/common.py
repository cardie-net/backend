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
    description: str | None = None
    cover_image_url: str | None = None

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 500:
            raise ValueError("Description must be 500 characters or fewer")
        return v


SOCIAL_PLATFORM_PATTERNS: dict[str, re.Pattern] = {
    "website": re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE),
    "github": re.compile(
        r"^https?://(www\.)?github\.com/[a-zA-Z0-9_.-]+/?$", re.IGNORECASE
    ),
    "twitter": re.compile(
        r"^https?://(www\.)?(twitter\.com|x\.com)/[a-zA-Z0-9_.-]+/?$", re.IGNORECASE
    ),
    "instagram": re.compile(
        r"^https?://(www\.)?instagram\.com/[a-zA-Z0-9_.-]+/?$", re.IGNORECASE
    ),
    "youtube": re.compile(
        r"^https?://(www\.)?youtube\.com/(@[a-zA-Z0-9_.-]+|[a-zA-Z0-9_.-]+|c/[a-zA-Z0-9_.-]+|channel/[a-zA-Z0-9_.-]+|user/[a-zA-Z0-9_.-]+)/?$",
        re.IGNORECASE,
    ),
    "linkedin": re.compile(
        r"^https?://(www\.)?linkedin\.com/in/[a-zA-Z0-9_.-]+/?$", re.IGNORECASE
    ),
    "tiktok": re.compile(
        r"^https?://(www\.)?tiktok\.com/(@[a-zA-Z0-9_.-]+|[a-zA-Z0-9_.-]+)/?$",
        re.IGNORECASE,
    ),
    "facebook": re.compile(
        r"^https?://(www\.)?facebook\.com/[a-zA-Z0-9_.-]+/?$", re.IGNORECASE
    ),
}
ALLOWED_SOCIAL_PLATFORMS = set(SOCIAL_PLATFORM_PATTERNS.keys())


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
            if value is not None:
                pattern = SOCIAL_PLATFORM_PATTERNS.get(platform, URL_PATTERN)
                if not pattern.match(value):
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
