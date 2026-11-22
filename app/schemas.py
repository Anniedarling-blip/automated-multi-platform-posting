"""API request and response schemas."""

import ipaddress
import re
from datetime import date as Date, time as Time
from enum import Enum
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


class Platform(str, Enum):
    """Supported publishing targets for future platform adapters."""

    LINKEDIN = "linkedin"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    BLUESKY = "bluesky"
    MASTODON = "mastodon"
    SLACK = "slack"


_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRAILING_SENTENCE_PUNCTUATION = ".,;:!?)]}"


def extract_cta_url(message: str) -> str:
    """Return the sole HTTP(S) URL in a message after validating its hostname."""
    matches = [
        match.group(0).rstrip(_TRAILING_SENTENCE_PUNCTUATION)
        for match in _URL_PATTERN.finditer(message)
    ]
    if len(matches) != 1:
        raise ValueError("message must contain exactly one HTTP or HTTPS URL")

    url = matches[0]
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        # Accessing .port validates its syntax and range.
        parsed.port
    except ValueError as exc:
        raise ValueError("URL must be valid and contain a valid hostname") from exc

    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        raise ValueError("URL must be valid and contain a valid hostname")

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        try:
            ascii_hostname = hostname.rstrip(".").encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("URL must contain a valid hostname") from exc
        if not ascii_hostname or len(ascii_hostname) > 253:
            raise ValueError("URL must contain a valid hostname")
        labels = ascii_hostname.split(".")
        if any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not re.fullmatch(r"[A-Za-z0-9-]+", label)
            for label in labels
        ):
            raise ValueError("URL must contain a valid hostname")

    return url


class PostingRequest(BaseModel):
    """The public request body contains only the post message."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=200)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty")
        extract_cta_url(value)
        return value


class PlatformResult(BaseModel):
    """A per-platform result shape for confirmed future publishing outcomes."""

    platform: Platform
    status: str
    posted_url: AnyHttpUrl | None = None
    public_access: bool | None = None
    date: Date | None = None
    time: Time | None = None
    error: str | None = None


class PostingResponse(BaseModel):
    """Per-platform publishing results; never populated with simulated results."""

    results: list[PlatformResult] = Field(min_length=1)


class ErrorResponse(BaseModel):
    """Standard FastAPI error payload."""

    detail: str

