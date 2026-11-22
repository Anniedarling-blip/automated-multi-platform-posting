"""Publish text messages through Slack Incoming Webhooks."""

from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

import httpx

from app.platforms.base import PlatformPublisher
from app.schemas import Platform, PlatformResult, PostingRequest

_WEBHOOK_PATH = re.compile(r"^/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[^/]+$")
_ALLOWED_HOSTS = {"hooks.slack.com", "hooks.slack-gov.com"}


class SlackPublisher(PlatformPublisher):
    """Send a validated message to a configured Slack webhook."""

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
        return Platform.SLACK

    async def publish(self, request: PostingRequest) -> PlatformResult:
        if not self._webhook_url:
            return self._failure("Slack webhook configuration is missing.")
        webhook_url = self._valid_webhook_url(self._webhook_url)
        if webhook_url is None:
            return self._failure("Slack webhook URL is invalid.")

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(webhook_url, json={"text": request.message})
        except httpx.TimeoutException:
            return self._failure("Slack request timed out.")
        except httpx.RequestError:
            return self._failure("Slack request failed due to a network error.")

        if response.status_code != 200:
            return self._failure(f"Slack returned HTTP {response.status_code}.")
        if response.text != "ok":
            return self._failure("Slack returned an unexpected response.")

        now = datetime.now(timezone.utc)
        return PlatformResult(
            platform=Platform.SLACK,
            status="posted",
            posted_url=None,
            public_access=None,
            date=now.date(),
            time=now.timetz(),
            error=None,
        )

    @staticmethod
    def _valid_webhook_url(value: str) -> str | None:
        normalized = value.strip()
        try:
            parsed = urlsplit(normalized)
            port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme.lower() != "https"
            or parsed.hostname not in _ALLOWED_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
            or parsed.query
            or parsed.fragment
            or not _WEBHOOK_PATH.fullmatch(parsed.path)
        ):
            return None
        return normalized

    @staticmethod
    def _failure(error: str) -> PlatformResult:
        return PlatformResult(
            platform=Platform.SLACK,
            status="failed",
            posted_url=None,
            public_access=None,
            date=None,
            time=None,
            error=error,
        )
