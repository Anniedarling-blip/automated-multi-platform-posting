"""Mastodon status publishing through its REST API."""

from datetime import datetime, timezone
import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.platforms.base import PlatformPublisher
from app.schemas import Platform, PlatformResult, PostingRequest


class MastodonPublisher(PlatformPublisher):
    """Publish public text statuses on a configured Mastodon instance."""

    def __init__(
        self,
        base_url: str | None,
        access_token: str | None,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._access_token = access_token
        self._timeout = timeout
        self._transport = transport

    @property
    def platform(self) -> Platform:
        return Platform.MASTODON

    async def publish(self, request: PostingRequest) -> PlatformResult:
        if not self._base_url or not self._access_token:
            return self._failure("Mastodon configuration is incomplete.")

        normalized_base_url = self._normalize_base_url(self._base_url)
        if normalized_base_url is None:
            return self._failure("Mastodon instance URL is invalid.")

        endpoint = f"{normalized_base_url}/api/v1/statuses"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    data={"status": request.message, "visibility": "public"},
                )
        except httpx.TimeoutException:
            return self._failure("Mastodon request timed out.")
        except httpx.RequestError:
            return self._failure("Mastodon request failed due to a network error.")

        if response.status_code in {401, 403}:
            return self._failure("Mastodon rejected the access token.")
        if response.status_code == 429:
            return self._failure("Mastodon rate limit exceeded.")
        if not response.is_success:
            return self._failure(
                f"Mastodon API error (HTTP {response.status_code})."
            )

        try:
            body: Any = response.json()
        except ValueError:
            return self._failure("Mastodon returned an invalid status response.")
        if not isinstance(body, dict):
            return self._failure("Mastodon returned an invalid status response.")

        status_id = body.get("id")
        status_url = body.get("url")
        created_at_value = body.get("created_at")
        if (
            isinstance(status_id, bool)
            or not isinstance(status_id, (str, int))
            or not str(status_id).strip()
        ):
            return self._failure("Mastodon response is missing the created status ID.")
        if not isinstance(status_url, str) or not status_url.strip():
            return self._failure("Mastodon response is missing the status URL.")
        if not isinstance(created_at_value, str):
            return self._failure("Mastodon response is missing the creation time.")

        try:
            created_at = datetime.fromisoformat(
                created_at_value.replace("Z", "+00:00")
            )
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            created_at = created_at.astimezone(timezone.utc)
        except ValueError:
            return self._failure("Mastodon returned an invalid creation time.")

        visibility = body.get("visibility")
        public_access = (
            True
            if visibility == "public"
            else False
            if visibility in ("unlisted", "private", "direct")
            else None
        )

        try:
            return PlatformResult(
                platform=Platform.MASTODON,
                status="posted",
                posted_url=status_url,
                public_access=public_access,
                date=created_at.date(),
                time=created_at.timetz(),
                error=None,
            )
        except ValidationError:
            return self._failure("Mastodon returned an invalid status URL.")

    @staticmethod
    def _normalize_base_url(base_url: str) -> str | None:
        normalized = base_url.strip().rstrip("/")
        if not normalized:
            return None

        try:
            parsed = urlsplit(normalized)
            port = parsed.port
            hostname = parsed.hostname
        except ValueError:
            return None

        if (
            parsed.scheme.lower() != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
            or parsed.query
            or parsed.fragment
        ):
            return None

        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            try:
                ascii_hostname = hostname.rstrip(".").encode("idna").decode("ascii")
            except UnicodeError:
                return None
            if not ascii_hostname or len(ascii_hostname) > 253:
                return None
            labels = ascii_hostname.split(".")
            if any(
                not label
                or len(label) > 63
                or label.startswith("-")
                or label.endswith("-")
                or not re.fullmatch(r"[A-Za-z0-9-]+", label)
                for label in labels
            ):
                return None

        return normalized

    @staticmethod
    def _failure(error: str) -> PlatformResult:
        return PlatformResult(
            platform=Platform.MASTODON,
            status="failed",
            posted_url=None,
            public_access=None,
            date=None,
            time=None,
            error=error,
        )
