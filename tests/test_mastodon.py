"""Mastodon status tests using mocked HTTPX transports only."""

import asyncio
from datetime import date, time, timezone

import httpx
import pytest

from app.config import Settings
from app.main import posting_service
from app.platforms.bluesky import BlueskyPublisher
from app.platforms.discord import DiscordPublisher
from app.platforms.mastodon import MastodonPublisher
from app.platforms.telegram import TelegramPublisher
from app.schemas import Platform, PostingRequest
from app.services.posting_service import PostingService

BASE_URL = "https://mastodon.example"
ACCESS_TOKEN = "test-mastodon-access-token"
STATUS_URL = f"{BASE_URL}/api/v1/statuses"


def posting_request() -> PostingRequest:
    return PostingRequest(message="Check out the update: https://example.com")


def test_mastodon_and_existing_adapters_are_registered() -> None:
    expected = {
        Platform.MASTODON,
        Platform.TELEGRAM,
        Platform.DISCORD,
        Platform.BLUESKY,
    }

    assert expected.issubset(posting_service._publishers)
    assert expected.issubset(posting_service._target_platforms)


def test_target_platform_settings_accept_mastodon_alongside_existing_platforms() -> None:
    settings = Settings(
        _env_file=None,
        target_platforms=["telegram", "discord", "bluesky", "mastodon"],
    )

    assert settings.target_platforms == [
        Platform.TELEGRAM,
        Platform.DISCORD,
        Platform.BLUESKY,
        Platform.MASTODON,
    ]


def created_status(*, visibility: str = "public") -> dict[str, object]:
    return {
        "id": "114000000000000000",
        "url": "https://mastodon.example/@writer/114000000000000000",
        "created_at": "2025-04-05T06:07:08.123Z",
        "visibility": visibility,
    }


def test_publishes_public_status_with_confirmed_response_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(api_request: httpx.Request) -> httpx.Response:
        requests.append(api_request)
        return httpx.Response(200, json=created_status())

    publisher = MastodonPublisher(
        f" {BASE_URL}/// ",
        ACCESS_TOKEN,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(publisher.publish(posting_request()))

    assert len(requests) == 1
    assert str(requests[0].url) == STATUS_URL
    assert requests[0].method == "POST"
    assert requests[0].headers["Authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert requests[0].headers["Content-Type"].startswith(
        "application/x-www-form-urlencoded"
    )
    assert dict(httpx.QueryParams(requests[0].content.decode())) == {
        "status": posting_request().message,
        "visibility": "public",
    }
    assert result.platform == Platform.MASTODON
    assert result.status == "posted"
    assert str(result.posted_url) == created_status()["url"]
    assert result.public_access is True
    assert result.date == date(2025, 4, 5)
    assert result.time == time(6, 7, 8, 123000, tzinfo=timezone.utc)
    assert result.error is None


def test_settings_normalize_mastodon_base_url_and_protect_token() -> None:
    settings = Settings(
        _env_file=None,
        mastodon_base_url=f"  {BASE_URL}///  ",
        mastodon_access_token=f"  {ACCESS_TOKEN}  ",
    )

    assert settings.mastodon_base_url == BASE_URL
    assert settings.mastodon_access_token is not None
    assert settings.mastodon_access_token.get_secret_value() == ACCESS_TOKEN


def test_missing_configuration_returns_failure_without_request() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("No request should be made without Mastodon configuration")

    result = asyncio.run(
        MastodonPublisher(
            None,
            None,
            transport=httpx.MockTransport(handler),
        ).publish(posting_request())
    )

    assert result.platform == Platform.MASTODON
    assert result.status == "failed"
    assert "configuration" in (result.error or "")


@pytest.mark.parametrize(
    "base_url",
    [
        "http://mastodon.example",
        "https:///missing-host",
        "https://bad_host.example",
        "https://user:pass@mastodon.example",
        "https://mastodon.example:444",
        "https://mastodon.example?query=value",
        "not a URL",
    ],
)
def test_invalid_instance_url_fails_without_request(base_url: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("An invalid instance URL must not be requested")

    result = asyncio.run(
        MastodonPublisher(
            base_url,
            ACCESS_TOKEN,
            transport=httpx.MockTransport(handler),
        ).publish(posting_request())
    )

    assert result.status == "failed"
    assert result.error == "Mastodon instance URL is invalid."


@pytest.mark.parametrize("status_code", [401, 403])
def test_authentication_failures_are_reported_without_token_leak(
    status_code: int,
) -> None:
    publisher = MastodonPublisher(
        BASE_URL,
        ACCESS_TOKEN,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status_code, json={"error": "invalid_token"})
        ),
    )

    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "failed"
    assert "rejected the access token" in (result.error or "")
    assert ACCESS_TOKEN not in (result.error or "")


def test_rate_limit_is_reported() -> None:
    publisher = MastodonPublisher(
        BASE_URL,
        ACCESS_TOKEN,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(429, json={"error": "rate limited"})
        ),
    )

    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "failed"
    assert "rate limit" in (result.error or "")


@pytest.mark.parametrize("status_code", [400, 500])
def test_other_api_errors_are_per_platform_failures(status_code: int) -> None:
    publisher = MastodonPublisher(
        BASE_URL,
        ACCESS_TOKEN,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status_code, json={"error": "api error"})
        ),
    )

    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "failed"
    assert f"HTTP {status_code}" in (result.error or "")


@pytest.mark.parametrize("failure_kind", ["timeout", "network"])
def test_timeout_and_network_failures_are_reported(failure_kind: str) -> None:
    def handler(api_request: httpx.Request) -> httpx.Response:
        if failure_kind == "timeout":
            raise httpx.ReadTimeout("timeout", request=api_request)
        raise httpx.ConnectError("connection failed", request=api_request)

    publisher = MastodonPublisher(
        BASE_URL,
        ACCESS_TOKEN,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "failed"
    if failure_kind == "timeout":
        assert "timed out" in (result.error or "")
    else:
        assert "network error" in (result.error or "")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not JSON"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"id": "1", "url": "https://mastodon.example/@a/1"}),
        httpx.Response(
            200,
            json={
                "id": "1",
                "url": "not a URL",
                "created_at": "2025-04-05T06:07:08Z",
            },
        ),
        httpx.Response(
            200,
            json={
                "id": "1",
                "url": "https://mastodon.example/@a/1",
                "created_at": "invalid",
            },
        ),
    ],
)
def test_malformed_api_responses_never_report_success(
    response: httpx.Response,
) -> None:
    publisher = MastodonPublisher(
        BASE_URL,
        ACCESS_TOKEN,
        transport=httpx.MockTransport(lambda _: response),
    )

    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "failed"
    assert result.posted_url is None


@pytest.mark.parametrize(
    ("visibility", "expected_public"),
    [("public", True), ("unlisted", False), (None, None)],
)
def test_public_access_only_reflects_confirmed_visibility(
    visibility: str | None,
    expected_public: bool | None,
) -> None:
    payload = created_status()
    if visibility is None:
        del payload["visibility"]
    else:
        payload["visibility"] = visibility
    publisher = MastodonPublisher(
        BASE_URL,
        ACCESS_TOKEN,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )

    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "posted"
    assert result.public_access is expected_public


def test_mastodon_failure_does_not_block_existing_publishers() -> None:
    mastodon = MastodonPublisher(
        BASE_URL,
        ACCESS_TOKEN,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(401, json={"error": "invalid_token"})
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
    bluesky = BlueskyPublisher(
        "writer.example",
        "test-app-password",
        transport=httpx.MockTransport(
            lambda api_request: httpx.Response(
                200,
                json=(
                    {
                        "accessJwt": "test-jwt",
                        "did": "did:plc:test",
                        "handle": "writer.example",
                    }
                    if api_request.url.path.endswith("createSession")
                    else {
                        "uri": "at://did:plc:test/app.bsky.feed.post/key",
                        "cid": "test-cid",
                    }
                ),
            )
        ),
    )
    service = PostingService(
        target_platforms=[
            Platform.MASTODON,
            Platform.TELEGRAM,
            Platform.DISCORD,
            Platform.BLUESKY,
        ],
        publishers={
            Platform.MASTODON: mastodon,
            Platform.TELEGRAM: telegram,
            Platform.DISCORD: discord,
            Platform.BLUESKY: bluesky,
        },
    )

    response = asyncio.run(service.publish(posting_request()))

    assert [result.platform for result in response.results] == [
        Platform.MASTODON,
        Platform.TELEGRAM,
        Platform.DISCORD,
        Platform.BLUESKY,
    ]
    assert [result.status for result in response.results] == [
        "failed",
        "posted",
        "posted",
        "posted",
    ]
