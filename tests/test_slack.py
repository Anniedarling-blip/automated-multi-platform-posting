"""Slack webhook publisher tests use mocked HTTPX transports only."""

import asyncio

import httpx
import pytest

from app.config import Settings
from app.main import posting_service
from app.platforms.slack import SlackPublisher
from app.platforms.telegram import TelegramPublisher
from app.schemas import Platform, PostingRequest
from app.services.posting_service import PostingService

WEBHOOK_URL = "https://hooks.slack.com/services/T01234567/B01234567/test-token"
MESSAGE = "Check out our latest business platform. https://example.com"


def test_slack_success_posts_json_and_returns_accurate_result():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == WEBHOOK_URL
        assert request.read() == httpx.Request(
            "POST", WEBHOOK_URL, json={"text": MESSAGE}
        ).read()
        return httpx.Response(200, text="ok")

    result = asyncio.run(
        SlackPublisher(WEBHOOK_URL, transport=httpx.MockTransport(handler)).publish(
            PostingRequest(message=MESSAGE)
        )
    )
    assert result.platform == Platform.SLACK
    assert result.status == "posted"
    assert result.posted_url is None
    assert result.public_access is None
    assert result.date and result.time
    assert result.error is None


@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.slack.com/services/T1/B2/token",
        "https://example.com/services/T1/B2/token",
        "https://hooks.slack.com/other/T1/B2/token",
        "https://hooks.slack.com/services/team/channel/token",
        "https://user@hooks.slack.com/services/T1/B2/token",
        "https://hooks.slack.com:444/services/T1/B2/token",
        "https://hooks.slack.com/services/T1/B2/token?x=1",
    ],
)
def test_invalid_webhook_url_fails_without_request(url):
    def handler(request):
        pytest.fail("Invalid URL must not make a network request")

    result = asyncio.run(
        SlackPublisher(url, transport=httpx.MockTransport(handler)).publish(
            PostingRequest(message=MESSAGE)
        )
    )
    assert result.status == "failed"
    assert result.error == "Slack webhook URL is invalid."


def test_missing_configuration_fails_without_request():
    result = asyncio.run(SlackPublisher(None).publish(PostingRequest(message=MESSAGE)))
    assert result.status == "failed"
    assert "missing" in result.error


@pytest.mark.parametrize(
    "response",
    [httpx.Response(403, text="no"), httpx.Response(200, text="OK"), httpx.Response(200, text="ok\n")],
)
def test_http_error_or_unexpected_body_is_failure(response):
    publisher = SlackPublisher(
        WEBHOOK_URL, transport=httpx.MockTransport(lambda request: response)
    )
    result = asyncio.run(publisher.publish(PostingRequest(message=MESSAGE)))
    assert result.status == "failed"
    assert result.posted_url is None


@pytest.mark.parametrize("exception", [httpx.ReadTimeout("timeout"), httpx.ConnectError("offline")])
def test_timeout_and_network_failure_are_reported(exception):
    def handler(request):
        raise exception

    result = asyncio.run(
        SlackPublisher(WEBHOOK_URL, transport=httpx.MockTransport(handler)).publish(
            PostingRequest(message=MESSAGE)
        )
    )
    assert result.status == "failed"


def test_failure_does_not_prevent_other_platforms():
    def telegram_handler(request):
        return httpx.Response(
            200,
            json={"ok": True, "result": {"message_id": 44, "chat": {"id": 1}}},
        )

    service = PostingService(
        [Platform.SLACK, Platform.TELEGRAM],
        {
            Platform.SLACK: SlackPublisher(
                WEBHOOK_URL, transport=httpx.MockTransport(lambda request: httpx.Response(500))
            ),
            Platform.TELEGRAM: TelegramPublisher(
                "test-token", "test-chat", transport=httpx.MockTransport(telegram_handler)
            ),
        },
    )
    results = asyncio.run(service.publish(PostingRequest(message=MESSAGE))).results
    assert [result.status for result in results] == ["failed", "posted"]


def test_configuration_accepts_slack_and_registry_keeps_all_integrations():
    settings = Settings(
        _env_file=None,
        target_platforms=["telegram", "discord", "bluesky", "mastodon", "slack"],
    )
    assert Platform.SLACK in settings.target_platforms
    assert {
        Platform.TELEGRAM,
        Platform.DISCORD,
        Platform.BLUESKY,
        Platform.MASTODON,
        Platform.SLACK,
    }.issubset(posting_service._publishers)
