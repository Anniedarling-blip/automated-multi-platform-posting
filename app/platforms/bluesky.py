"""Bluesky publishing through the AT Protocol XRPC endpoints."""

from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.platforms.base import PlatformPublisher
from app.schemas import Platform, PlatformResult, PostingRequest

_API_ROOT = "https://bsky.social/xrpc"
_CREATE_SESSION = f"{_API_ROOT}/com.atproto.server.createSession"
_CREATE_RECORD = f"{_API_ROOT}/com.atproto.repo.createRecord"
_POST_COLLECTION = "app.bsky.feed.post"


class BlueskyPublisher(PlatformPublisher):
    """Authenticate with an app password and create a public feed-post record."""

    def __init__(
        self,
        handle: str | None,
        app_password: str | None,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._handle = handle.strip() if handle else None
        self._app_password = app_password.strip() if app_password else None
        self._timeout = timeout
        self._transport = transport

    @property
    def platform(self) -> Platform:
        return Platform.BLUESKY

    async def publish(self, request: PostingRequest) -> PlatformResult:
        if not self._handle or not self._app_password:
            return self._failure("Bluesky credentials are not configured.")

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                try:
                    session_response = await client.post(
                        _CREATE_SESSION,
                        json={
                            "identifier": self._handle,
                            "password": self._app_password,
                        },
                    )
                except httpx.TimeoutException:
                    return self._failure("Bluesky authentication timed out.")
                except httpx.RequestError:
                    return self._failure(
                        "Bluesky authentication failed due to a network error."
                    )

                session_body = self._json_object(session_response)
                if not session_response.is_success:
                    return self._failure(
                        f"Bluesky authentication failed (HTTP {session_response.status_code})."
                    )
                if session_body is None:
                    return self._failure(
                        "Bluesky returned an invalid authentication response."
                    )

                access_jwt = session_body.get("accessJwt")
                account_did = session_body.get("did")
                authenticated_handle = session_body.get("handle")
                if not all(
                    isinstance(value, str) and value.strip()
                    for value in (access_jwt, account_did, authenticated_handle)
                ):
                    return self._failure(
                        "Bluesky authentication response is missing session details."
                    )

                created_at = datetime.now(timezone.utc)
                created_at = created_at.replace(
                    microsecond=(created_at.microsecond // 1000) * 1000
                )
                created_at_iso = created_at.isoformat(timespec="milliseconds").replace(
                    "+00:00", "Z"
                )
                record_payload = {
                    "repo": account_did,
                    "collection": _POST_COLLECTION,
                    "record": {
                        "text": request.message,
                        "createdAt": created_at_iso,
                    },
                }
                try:
                    record_response = await client.post(
                        _CREATE_RECORD,
                        headers={"Authorization": f"Bearer {access_jwt}"},
                        json=record_payload,
                    )
                except httpx.TimeoutException:
                    return self._failure("Bluesky post creation timed out.")
                except httpx.RequestError:
                    return self._failure(
                        "Bluesky post creation failed due to a network error."
                    )

        except httpx.TimeoutException:
            return self._failure("Bluesky request timed out.")
        except httpx.RequestError:
            return self._failure("Bluesky request failed due to a network error.")

        record_body = self._json_object(record_response)
        if not record_response.is_success:
            return self._failure(
                f"Bluesky post creation failed (HTTP {record_response.status_code})."
            )
        if record_body is None:
            return self._failure("Bluesky returned an invalid record response.")

        uri = record_body.get("uri")
        cid = record_body.get("cid")
        expected_prefix = f"at://{account_did}/{_POST_COLLECTION}/"
        if (
            not isinstance(uri, str)
            or not uri.startswith(expected_prefix)
            or not isinstance(cid, str)
            or not cid.strip()
        ):
            return self._failure(
                "Bluesky did not confirm the created post record."
            )

        record_key = uri[len(expected_prefix) :]
        if not record_key or "/" in record_key:
            return self._failure("Bluesky returned an invalid post record URI.")

        profile_handle = quote(authenticated_handle.strip(), safe=".-_")
        post_url = f"https://bsky.app/profile/{profile_handle}/post/{quote(record_key, safe='.-_')}"
        return PlatformResult(
            platform=Platform.BLUESKY,
            status="posted",
            posted_url=post_url,
            public_access=True,
            date=created_at.date(),
            time=created_at.timetz(),
            error=None,
        )

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any] | None:
        try:
            body = response.json()
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    @staticmethod
    def _failure(error: str) -> PlatformResult:
        return PlatformResult(
            platform=Platform.BLUESKY,
            status="failed",
            posted_url=None,
            public_access=None,
            date=None,
            time=None,
            error=error,
        )
