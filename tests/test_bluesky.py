"""Bluesky XRPC tests using mocked HTTPX transports only."""

import asyncio
from datetime import datetime, timezone
import json

import httpx
import pytest

from app.platforms.bluesky import BlueskyPublisher
from app.platforms.discord import DiscordPublisher
from app.platforms.telegram import TelegramPublisher
from app.main import posting_service
from app.schemas import Platform, PlatformResult, PostingRequest
from app.services.posting_service import PostingService

SESSION_URL = "https://bsky.social/xrpc/com.atproto.server.createSession"
RECORD_URL = "https://bsky.social/xrpc/com.atproto.repo.createRecord"
HANDLE = "writer.example"
APP_PASSWORD = "test-app-password"
DID = "did:plc:exampleaccount"


def posting_request() -> PostingRequest:
    return PostingRequest(message="Check out the update: https://example.com")


def test_bluesky_is_registered_for_configured_target() -> None:
    assert Platform.BLUESKY in posting_service._target_platforms
    assert Platform.BLUESKY in posting_service._publishers


def session_response() -> dict[str, str]:
    return {
        "accessJwt": "test-access-jwt",
        "refreshJwt": "test-refresh-jwt",
        "did": DID,
        "handle": HANDLE,
    }


def record_response(
    *,
    uri: str = f"at://{DID}/app.bsky.feed.post/3lxyzabc",
    cid: str = "bafyreitestcid",
) -> dict[str, str]:
    return {"uri": uri, "cid": cid}


def test_authenticates_and_creates_record_with_public_post_url() -> None:
    requests: list[httpx.Request] = []

    def handler(api_request: httpx.Request) -> httpx.Response:
        requests.append(api_request)
        if str(api_request.url) == SESSION_URL:
            return httpx.Response(200, json=session_response())
        return httpx.Response(200, json=record_response())

    publisher = BlueskyPublisher(
        HANDLE,
        APP_PASSWORD,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(publisher.publish(posting_request()))

    assert [str(api_request.url) for api_request in requests] == [
        SESSION_URL,
        RECORD_URL,
    ]
    auth_payload = json.loads(requests[0].content)
    assert auth_payload == {"identifier": HANDLE, "password": APP_PASSWORD}
    record_payload = json.loads(requests[1].content)
    assert record_payload["repo"] == DID
    assert record_payload["collection"] == "app.bsky.feed.post"
    assert record_payload["record"]["text"] == posting_request().message
    created_at = datetime.fromisoformat(
        record_payload["record"]["createdAt"].replace("Z", "+00:00")
    )
    assert created_at.tzinfo == timezone.utc
    assert requests[1].headers["Authorization"] == "Bearer test-access-jwt"
    assert result.platform == Platform.BLUESKY
    assert result.status == "posted"
    assert str(result.posted_url) == (
        "https://bsky.app/profile/writer.example/post/3lxyzabc"
    )
    assert result.public_access is True
    assert result.date == created_at.date()
    assert result.time == created_at.timetz()
    assert result.error is None


def test_missing_credentials_fails_without_http_requests() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("No HTTP request should be made without credentials")

    publisher = BlueskyPublisher(
        None,
        None,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(publisher.publish(posting_request()))

    assert result.platform == Platform.BLUESKY
    assert result.status == "failed"
    assert "credentials" in (result.error or "")


@pytest.mark.parametrize("status_code", [400, 401, 403, 500])
def test_authentication_errors_do_not_create_a_record(status_code: int) -> None:
    requests: list[str] = []

    def handler(api_request: httpx.Request) -> httpx.Response:
        requests.append(str(api_request.url))
        return httpx.Response(status_code, json={"error": "AuthError"})

    publisher = BlueskyPublisher(
        HANDLE,
        APP_PASSWORD,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(publisher.publish(posting_request()))

    assert requests == [SESSION_URL]
    assert result.status == "failed"
    assert "authentication failed" in (result.error or "")
    assert APP_PASSWORD not in (result.error or "")


def test_record_api_error_returns_failure() -> None:
    def handler(api_request: httpx.Request) -> httpx.Response:
        if str(api_request.url) == SESSION_URL:
            return httpx.Response(200, json=session_response())
        return httpx.Response(400, json={"error": "InvalidRecord"})

    publisher = BlueskyPublisher(
        HANDLE,
        APP_PASSWORD,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "failed"
    assert "post creation failed (HTTP 400)" in (result.error or "")


@pytest.mark.parametrize(
    ("failure_phase", "failure_kind"),
    [
        ("session", "timeout"),
        ("session", "network"),
        ("record", "timeout"),
        ("record", "network"),
    ],
)
def test_timeout_and_network_failures_are_isolated(
    failure_phase: str,
    failure_kind: str,
) -> None:
    def handler(api_request: httpx.Request) -> httpx.Response:
        is_session = str(api_request.url) == SESSION_URL
        if failure_phase == "session" or not is_session:
            if failure_kind == "timeout":
                raise httpx.ReadTimeout("timeout", request=api_request)
            raise httpx.ConnectError("connection error", request=api_request)
        return httpx.Response(200, json=session_response())

    publisher = BlueskyPublisher(
        HANDLE,
        APP_PASSWORD,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "failed"
    assert result.error is not None
    assert "timed out" in result.error if failure_kind == "timeout" else "network error" in result.error


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"accessJwt": "token"}),
        httpx.Response(200, text="not JSON"),
    ],
)
def test_invalid_session_response_fails(response: httpx.Response) -> None:
    publisher = BlueskyPublisher(
        HANDLE,
        APP_PASSWORD,
        transport=httpx.MockTransport(lambda _: response),
    )

    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "failed"
    assert "authentication" in (result.error or "")


@pytest.mark.parametrize(
    "payload",
    [
        {"uri": f"at://{DID}/app.bsky.feed.post/3lxyzabc"},
        {"uri": "at://did:plc:other/app.bsky.feed.post/3lxyzabc", "cid": "cid"},
        {"uri": f"at://{DID}/app.bsky.feed.like/3lxyzabc", "cid": "cid"},
        {"uri": f"at://{DID}/app.bsky.feed.post/", "cid": "cid"},
    ],
)
def test_unconfirmed_or_invalid_record_result_never_reports_success(
    payload: dict[str, str],
) -> None:
    def handler(api_request: httpx.Request) -> httpx.Response:
        if str(api_request.url) == SESSION_URL:
            return httpx.Response(200, json=session_response())
        return httpx.Response(200, json=payload)

    publisher = BlueskyPublisher(
        HANDLE,
        APP_PASSWORD,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "failed"
    assert result.posted_url is None


def test_bluesky_failure_does_not_block_telegram_or_discord() -> None:
    bluesky = BlueskyPublisher(
        HANDLE,
        APP_PASSWORD,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(401, json={"error": "AuthenticationRequired"})
        ),
    )
    telegram = TelegramPublisher(
        "test-token",
        "@test_channel",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": 20,
                        "date": 1_700_000_000,
                        "chat": {
                            "id": -100123,
                            "type": "channel",
                            "username": "test_channel",
                        },
                    },
                },
            )
        ),
    )
    discord = DiscordPublisher(
        "https://discord.com/api/webhooks/123/test-token",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "id": "111111111111111111",
                    "channel_id": "222222222222222222",
                    "guild_id": "333333333333333333",
                    "timestamp": "2025-02-03T04:05:06Z",
                },
            )
        ),
    )
    service = PostingService(
        target_platforms=[Platform.BLUESKY, Platform.TELEGRAM, Platform.DISCORD],
        publishers={
            Platform.BLUESKY: bluesky,
            Platform.TELEGRAM: telegram,
            Platform.DISCORD: discord,
        },
    )

    response = asyncio.run(service.publish(posting_request()))

    assert [result.platform for result in response.results] == [
        Platform.BLUESKY,
        Platform.TELEGRAM,
        Platform.DISCORD,
    ]
    assert [result.status for result in response.results] == [
        "failed",
        "posted",
        "posted",
    ]
