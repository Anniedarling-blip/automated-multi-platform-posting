"""Discord Execute Webhook tests using HTTPX mock transports only."""

import asyncio
from datetime import date, time, timezone
import json

import httpx
import pytest

from app.platforms.discord import DiscordPublisher
from app.platforms.telegram import TelegramPublisher
from app.config import Settings
from app.schemas import Platform, PlatformResult, PostingRequest
from app.services.posting_service import PostingService

WEBHOOK_URL = "https://discord.com/api/webhooks/123456789012345678/test-webhook-token"
WEBHOOK_URL_WITH_QUERY = f"{WEBHOOK_URL}?wait=false&thread_id=444444444444444444"


def posting_request() -> PostingRequest:
    return PostingRequest(message="Check out the update: https://example.com")


def discord_message(*, include_guild_id: bool = True) -> dict[str, object]:
    message: dict[str, object] = {
        "id": "111111111111111111",
        "channel_id": "222222222222222222",
        "timestamp": "2025-02-03T04:05:06.123000+00:00",
        "content": "Check out the update: https://example.com",
    }
    if include_guild_id:
        message["guild_id"] = "333333333333333333"
    return message


def test_executes_webhook_with_wait_and_returns_confirmed_message() -> None:
    calls: list[httpx.Request] = []

    def handler(api_request: httpx.Request) -> httpx.Response:
        calls.append(api_request)
        return httpx.Response(200, json=discord_message())

    publisher = DiscordPublisher(
        WEBHOOK_URL_WITH_QUERY,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(publisher.publish(posting_request()))

    assert len(calls) == 1
    assert calls[0].method == "POST"
    assert calls[0].url.params.get("wait") == "true"
    assert calls[0].url.params.get("thread_id") == "444444444444444444"
    payload = json.loads(calls[0].content)
    assert payload["content"] == "Check out the update: https://example.com"
    assert payload["allowed_mentions"] == {"parse": []}
    assert result.platform == Platform.DISCORD
    assert result.status == "posted"
    assert str(result.posted_url) == (
        "https://discord.com/channels/333333333333333333/"
        "222222222222222222/111111111111111111"
    )
    assert result.public_access is None
    assert result.date == date(2025, 2, 3)
    assert result.time is not None and result.time.tzinfo == timezone.utc
    assert result.error is None


def test_success_without_guild_id_does_not_invent_message_url() -> None:
    publisher = DiscordPublisher(
        WEBHOOK_URL,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=discord_message(include_guild_id=False))
        ),
    )

    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "posted"
    assert result.posted_url is None
    assert result.public_access is None


def test_resolves_guild_id_for_permalink_from_webhook_metadata() -> None:
    def handler(api_request: httpx.Request) -> httpx.Response:
        if api_request.method == "POST":
            return httpx.Response(200, json=discord_message(include_guild_id=False))
        return httpx.Response(
            200,
            json={
                "id": "123456789012345678",
                "channel_id": "222222222222222222",
                "guild_id": "333333333333333333",
                "type": 1,
            },
        )

    publisher = DiscordPublisher(
        WEBHOOK_URL,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "posted"
    assert str(result.posted_url) == (
        "https://discord.com/channels/333333333333333333/"
        "222222222222222222/111111111111111111"
    )


def test_missing_webhook_configuration_returns_failure_without_request() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("No HTTP request should be made without a webhook URL")

    publisher = DiscordPublisher(None, transport=httpx.MockTransport(handler))
    result = asyncio.run(publisher.publish(posting_request()))

    assert result.platform == Platform.DISCORD
    assert result.status == "failed"
    assert "not configured" in (result.error or "")


def test_valid_official_webhook_url_with_query_parameters_is_accepted() -> None:
    endpoint = DiscordPublisher._validated_endpoint(WEBHOOK_URL_WITH_QUERY)

    assert endpoint == (
        "https://discord.com/api/webhooks/123456789012345678/"
        "test-webhook-token?thread_id=444444444444444444&wait=true"
    )


def test_valid_webhook_url_is_trimmed_in_environment_configuration() -> None:
    settings = Settings(
        _env_file=None,
        discord_webhook_url=f"  \ufeff\"{WEBHOOK_URL}\" \t\n",
    )

    assert settings.discord_webhook_url is not None
    assert settings.discord_webhook_url.get_secret_value() == WEBHOOK_URL


def test_direct_adapter_validation_strips_wrapping_quotes_and_whitespace() -> None:
    endpoint = DiscordPublisher._validated_endpoint(f"  '{WEBHOOK_URL}'  ")

    assert endpoint == f"{WEBHOOK_URL}?wait=true"


@pytest.mark.parametrize(
    "webhook_url",
    [
        "http://discord.com/api/webhooks/123/token",
        "https://evil.example/api/webhooks/123/token",
        "https://discord.com/not-a-webhook/123/token",
        "https://discord.com/api/webhooks/not-numeric/token",
        "https://discord.com/api/webhooks/123/",
        "https://discord.com:444/api/webhooks/123/token",
        "https://user:password@discord.com/api/webhooks/123/token",
        "https://discord.com/api/webhooks/123/token#fragment",
        "https://discord.com/api/webhooks/123/to\u200bken",
        'https://discord.com/api/webhooks/123/to"ken',
    ],
)
def test_invalid_webhook_url_fails_without_request(webhook_url: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid webhook URLs must not be requested")

    publisher = DiscordPublisher(
        webhook_url,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "failed"
    assert result.error == "Discord webhook URL is invalid."


@pytest.mark.parametrize("status_code", [400, 401, 404, 429, 500])
def test_http_errors_are_platform_failures(status_code: int) -> None:
    publisher = DiscordPublisher(
        WEBHOOK_URL,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                status_code,
                json={"message": "Webhook token is invalid"},
            )
        ),
    )

    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "failed"
    assert f"HTTP {status_code}" in (result.error or "")
    assert result.posted_url is None
    assert result.public_access is None


@pytest.mark.parametrize("failure_kind", ["timeout", "network"])
def test_timeout_and_network_failures_are_reported(failure_kind: str) -> None:
    def handler(api_request: httpx.Request) -> httpx.Response:
        if failure_kind == "timeout":
            raise httpx.ReadTimeout("timeout", request=api_request)
        raise httpx.ConnectError("connection error", request=api_request)

    publisher = DiscordPublisher(
        WEBHOOK_URL,
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
        httpx.Response(204),
        httpx.Response(200, json={"content": "accepted but missing ID"}),
        httpx.Response(200, text="not JSON"),
    ],
)
def test_unconfirmed_or_malformed_responses_never_report_success(
    response: httpx.Response,
) -> None:
    publisher = DiscordPublisher(
        WEBHOOK_URL,
        transport=httpx.MockTransport(lambda _: response),
    )

    result = asyncio.run(publisher.publish(posting_request()))

    assert result.status == "failed"
    assert result.error


def test_discord_failure_does_not_block_telegram_publishing() -> None:
    discord = DiscordPublisher(
        WEBHOOK_URL,
        transport=httpx.MockTransport(lambda _: httpx.Response(404, json={"message": "Not Found"})),
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
                        "chat": {"id": -100123, "type": "channel", "username": "test_channel"},
                    },
                },
            )
        ),
    )
    service = PostingService(
        target_platforms=[Platform.DISCORD, Platform.TELEGRAM],
        publishers={Platform.DISCORD: discord, Platform.TELEGRAM: telegram},
    )

    response = asyncio.run(service.publish(posting_request()))

    assert [result.platform for result in response.results] == [
        Platform.DISCORD,
        Platform.TELEGRAM,
    ]
    assert [result.status for result in response.results] == ["failed", "posted"]
