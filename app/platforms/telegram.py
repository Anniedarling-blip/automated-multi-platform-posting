"""Telegram Bot API publisher implemented with HTTPX."""

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.platforms.base import PlatformPublisher
from app.schemas import Platform, PlatformResult, PostingRequest


class TelegramPublisher(PlatformPublisher):
    """Send a message through Telegram's official Bot API."""

    def __init__(
        self,
        bot_token: str | None,
        chat_id: str | None,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._timeout = timeout
        self._transport = transport

    @property
    def platform(self) -> Platform:
        return Platform.TELEGRAM

    async def publish(self, request: PostingRequest) -> PlatformResult:
        if not self._bot_token or not self._chat_id:
            return self._failure("Telegram credentials are not configured.")

        endpoint = (
            f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        )
        payload = {"chat_id": self._chat_id, "text": request.message}

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(endpoint, json=payload)
        except httpx.TimeoutException:
            return self._failure("Telegram request timed out.")
        except httpx.RequestError:
            return self._failure("Telegram request failed due to a network error.")

        try:
            body: Any = response.json()
        except ValueError:
            return self._failure(
                f"Telegram returned an invalid response (HTTP {response.status_code})."
            )

        if not isinstance(body, dict):
            return self._failure("Telegram returned an invalid response.")

        api_error_code = body.get("error_code")
        if response.status_code == 401 or api_error_code == 401:
            return self._failure("Telegram rejected the bot token (unauthorized).")

        if response.is_error or body.get("ok") is not True:
            description = body.get("description")
            if isinstance(description, str) and description:
                safe_description = description.replace(self._bot_token, "[redacted]")
                detail = f"Telegram API error: {safe_description[:400]}"
            else:
                detail = f"Telegram API error (HTTP {response.status_code})."
            return self._failure(detail)

        message = body.get("result")
        if not isinstance(message, dict):
            return self._failure(
                "Telegram confirmed no usable message result was returned."
            )

        message_id = message.get("message_id")
        chat = message.get("chat")
        if (
            isinstance(message_id, bool)
            or not isinstance(message_id, int)
            or message_id < 1
            or not isinstance(chat, dict)
        ):
            return self._failure(
                "Telegram response was missing the sent message identifier or chat."
            )

        username = chat.get("username")
        chat_type = chat.get("type")
        is_public = (
            isinstance(username, str)
            and bool(username.strip())
            and chat_type in {"channel", "supergroup"}
        )
        posted_url = (
            f"https://t.me/{quote(username.lstrip('@'), safe='_')}/{message_id}"
            if is_public
            else None
        )

        posted_date = None
        posted_time = None
        timestamp = message.get("date")
        if isinstance(timestamp, int) and not isinstance(timestamp, bool):
            try:
                posted_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                posted_date = posted_at.date()
                posted_time = posted_at.timetz()
            except (OverflowError, OSError, ValueError):
                pass

        return PlatformResult(
            platform=Platform.TELEGRAM,
            status="posted",
            posted_url=posted_url,
            public_access=is_public,
            date=posted_date,
            time=posted_time,
            error=None,
        )

    @staticmethod
    def _failure(error: str) -> PlatformResult:
        return PlatformResult(
            platform=Platform.TELEGRAM,
            status="failed",
            posted_url=None,
            public_access=None,
            date=None,
            time=None,
            error=error,
        )
