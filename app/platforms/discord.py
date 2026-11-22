"""Discord Execute Webhook publisher implemented with HTTPX."""

from datetime import datetime, timezone
import re
from typing import Any
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.platforms.base import PlatformPublisher
from app.schemas import Platform, PlatformResult, PostingRequest

_WEBHOOK_PATH = re.compile(r"^/api/webhooks/[0-9]+/[^/]+/?$")
_EDGE_FORMAT_CHARACTERS = "\ufeff\u200b\u200c\u200d\u2060"


class DiscordPublisher(PlatformPublisher):
    """Publish plain-text messages through a configured Discord webhook."""

    def __init__(
        self,
        webhook_url: str | None,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._timeout = timeout
        self._transport = transport

    @property
    def platform(self) -> Platform:
        return Platform.DISCORD

    async def publish(self, request: PostingRequest) -> PlatformResult:
        if not self._webhook_url:
            return self._failure("Discord webhook URL is not configured.")

        endpoint = self._validated_endpoint(self._webhook_url)
        if endpoint is None:
            return self._failure("Discord webhook URL is invalid.")

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    endpoint,
                    json={
                        "content": request.message,
                        "allowed_mentions": {"parse": []},
                    },
                )
        except httpx.TimeoutException:
            return self._failure("Discord webhook request timed out.")
        except httpx.RequestError:
            return self._failure("Discord webhook request failed due to a network error.")

        try:
            body: Any = response.json()
        except ValueError:
            return self._failure(
                f"Discord returned an invalid response (HTTP {response.status_code})."
            )

        if not response.is_success:
            return self._failure(self._api_error(response.status_code))
        if not isinstance(body, dict):
            return self._failure("Discord returned an invalid message response.")

        message_id = self._snowflake(body.get("id"))
        if message_id is None:
            return self._failure(
                "Discord did not confirm the message with a valid message ID."
            )

        channel_id = self._snowflake(body.get("channel_id"))
        guild_id = self._snowflake(body.get("guild_id"))
        if channel_id is not None and guild_id is None:
            guild_id = await self._lookup_guild_id(endpoint)
        posted_url = (
            f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
            if guild_id and channel_id
            else None
        )

        posted_date = None
        posted_time = None
        timestamp = body.get("timestamp")
        if isinstance(timestamp, str):
            try:
                posted_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=timezone.utc)
                posted_at = posted_at.astimezone(timezone.utc)
                posted_date = posted_at.date()
                posted_time = posted_at.timetz()
            except ValueError:
                pass

        return PlatformResult(
            platform=Platform.DISCORD,
            status="posted",
            posted_url=posted_url,
            # Execute Webhook does not establish whether viewers can access the
            # guild/channel, so represent public access as unknown.
            public_access=None,
            date=posted_date,
            time=posted_time,
            error=None,
        )

    async def _lookup_guild_id(self, endpoint: str) -> str | None:
        """Resolve guild metadata for a message permalink when needed."""
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.get(endpoint)
            if not response.is_success:
                return None
            body = response.json()
        except (httpx.RequestError, ValueError):
            # The message is already confirmed; missing metadata only means
            # that a permalink cannot be constructed.
            return None

        if not isinstance(body, dict):
            return None
        return self._snowflake(body.get("guild_id"))

    @staticmethod
    def _validated_endpoint(webhook_url: str) -> str | None:
        webhook_url = webhook_url.strip().strip(_EDGE_FORMAT_CHARACTERS).strip()
        if len(webhook_url) >= 2 and webhook_url[0] == webhook_url[-1]:
            if webhook_url[0] in "\"'":
                webhook_url = (
                    webhook_url[1:-1]
                    .strip()
                    .strip(_EDGE_FORMAT_CHARACTERS)
                    .strip()
                )

        if any(unicodedata.category(char) in {"Cc", "Cf"} for char in webhook_url):
            return None

        try:
            parts = urlsplit(webhook_url)
            port = parts.port
        except ValueError:
            return None

        if (
            parts.scheme.lower() != "https"
            or parts.hostname is None
            or parts.hostname.lower() != "discord.com"
            or parts.username is not None
            or parts.password is not None
            or port not in (None, 443)
            or parts.fragment
            or "\"" in parts.path
            or "'" in parts.path
            or not _WEBHOOK_PATH.fullmatch(parts.path)
        ):
            return None

        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() != "wait"
        ]
        query.append(("wait", "true"))
        return urlunsplit(
            (
                "https",
                "discord.com",
                parts.path.rstrip("/"),
                urlencode(query),
                "",
            )
        )

    @staticmethod
    def _snowflake(value: Any) -> str | None:
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value) if value >= 0 else None
        if isinstance(value, str) and value.isdecimal():
            return value
        return None

    @staticmethod
    def _api_error(status_code: int) -> str:
        # Do not echo response detail that could contain webhook credentials.
        return f"Discord API error (HTTP {status_code})."

    @staticmethod
    def _failure(error: str) -> PlatformResult:
        return PlatformResult(
            platform=Platform.DISCORD,
            status="failed",
            posted_url=None,
            public_access=None,
            date=None,
            time=None,
            error=error,
        )
