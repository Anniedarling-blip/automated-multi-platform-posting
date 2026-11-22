"""Environment-backed application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas import Platform

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
_EDGE_FORMAT_CHARACTERS = "\ufeff\u200b\u200c\u200d\u2060"


def _normalize_webhook_value(value: str) -> str:
    value = value.strip().strip(_EDGE_FORMAT_CHARACTERS).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    value = value.strip().strip(_EDGE_FORMAT_CHARACTERS).strip()
    return value


class Settings(BaseSettings):
    app_name: str = "Automated Multi-Platform Posting System"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 4000
    target_platforms: list[Platform] = Field(
        default_factory=lambda: list(Platform), min_length=1
    )
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    discord_webhook_url: SecretStr | None = None
    slack_webhook_url: SecretStr | None = None
    bluesky_handle: str | None = None
    bluesky_app_password: SecretStr | None = None
    mastodon_base_url: str | None = None
    mastodon_access_token: SecretStr | None = None

    @field_validator("target_platforms")
    @classmethod
    def target_platforms_must_be_unique(cls, value: list[Platform]) -> list[Platform]:
        if len(value) != len(set(value)):
            raise ValueError("target_platforms must not contain duplicates")
        return value

    @field_validator("discord_webhook_url", mode="before")
    @classmethod
    def strip_discord_webhook_url(cls, value: object) -> object:
        if isinstance(value, str):
            value = _normalize_webhook_value(value)
            return value or None
        if isinstance(value, SecretStr):
            value = _normalize_webhook_value(value.get_secret_value())
            return value or None
        return value

    @field_validator("slack_webhook_url", mode="before")
    @classmethod
    def strip_slack_webhook_url(cls, value: object) -> object:
        if isinstance(value, str):
            value = _normalize_webhook_value(value)
            return value or None
        if isinstance(value, SecretStr):
            value = _normalize_webhook_value(value.get_secret_value())
            return value or None
        return value

    @field_validator("bluesky_handle", mode="before")
    @classmethod
    def strip_bluesky_handle(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("bluesky_app_password", mode="before")
    @classmethod
    def strip_bluesky_app_password(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        if isinstance(value, SecretStr):
            value = value.get_secret_value().strip()
            return value or None
        return value

    @field_validator("mastodon_base_url", mode="before")
    @classmethod
    def normalize_mastodon_base_url(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip().rstrip("/")
            return value or None
        return value

    @field_validator("mastodon_access_token", mode="before")
    @classmethod
    def strip_mastodon_access_token(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        if isinstance(value, SecretStr):
            value = value.get_secret_value().strip()
            return value or None
        return value

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings loaded from the environment and optional .env."""
    return Settings()

