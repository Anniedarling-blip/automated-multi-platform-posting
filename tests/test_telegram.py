"""Telegram publisher tests using HTTPX mock transports only."""

import asyncio
from datetime import date, time, timezone

import httpx
import pytest

from app.platforms.telegram import TelegramPublisher
from app.schemas import Platform, PlatformResult, PostingRequest
from app.services.posting_service import PostingService


def request() -> PostingRequest:
    return PostingRequest(message="Check our update: https://example.com")


def telegram_success(
    *,
    message_id: int = 731,
    timestamp: int = 1_700_000_000,
    chat: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "ok": True,
        "result": {
            "message_id": message_id,
            "date": timestamp,
            "chat": chat
            or {
                "id": -100123456,
                "type": "channel",
                "username": "sample_channel",
            },
        },
    }


def test_sends_message_and_returns_public_channel_url() -> None:
    sent: list[tuple[str, dict[str, object]]] = []

    def handler(api_request: httpx.Request) -> httpx.Response:
        import json

        sent.append((str(api_request.url), json.loads(api_request.content)))
        return httpx.Response(200, json=telegram_success())

    publisher = TelegramPublisher(
        "test-token",
        "@sample_channel",
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(publisher.publish(request()))

    assert sent[0][0].endswith("/bottest-token/sendMessage")
    assert sent[0][1] == {
        "chat_id": "@sample_channel",
        "text": "Check our update: https://example.com",
    }
    assert result.platform == Platform.TELEGRAM
    assert result.status == "posted"
    assert str(result.posted_url) == "https://t.me/sample_channel/731"
    assert result.public_access is True
    assert result.date == date(2023, 11, 14)
    assert result.time is not None and result.time.tzinfo == timezone.utc
    assert result.error is None


def test_private_chat_has_no_public_url() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=telegram_success(chat={"id": 123, "type": "private"}),
        )

    publisher = TelegramPublisher(
        "test-token", "123", transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(publisher.publish(request()))

    assert result.status == "posted"
    assert result.posted_url is None
    assert result.public_access is False


@pytest.mark.parametrize(
    ("status_code", "payload", "expected_error"),
    [
        (401, {"ok": False, "error_code": 401}, "unauthorized"),
        (
            400,
            {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"},
            "chat not found",
        ),
    ],
)
def test_handles_telegram_api_errors(
    status_code: int,
    payload: dict[str, object],
    expected_error: str,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    publisher = TelegramPublisher(
        "test-token", "@sample_channel", transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(publisher.publish(request()))

    assert result.status == "failed"
    assert result.posted_url is None
    assert result.public_access is None
    assert expected_error in (result.error or "").lower()


@pytest.mark.parametrize("failure_kind", ["timeout", "network"])
def test_handles_timeout_and_network_failures(failure_kind: str) -> None:
    def handler(api_request: httpx.Request) -> httpx.Response:
        if failure_kind == "timeout":
            raise httpx.ReadTimeout("timed out", request=api_request)
        raise httpx.ConnectError("connection failed", request=api_request)

    publisher = TelegramPublisher(
        "test-token", "@sample_channel", transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(publisher.publish(request()))

    assert result.status == "failed"
    assert result.error is not None
    assert "timed out" in result.error if failure_kind == "timeout" else "network" in result.error


def test_does_not_report_success_without_message_id() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        payload = telegram_success()
        del payload["result"]["message_id"]  # type: ignore[index]
        return httpx.Response(200, json=payload)

    publisher = TelegramPublisher(
        "test-token", "@sample_channel", transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(publisher.publish(request()))

    assert result.status == "failed"
    assert "identifier" in (result.error or "")


def test_missing_credentials_do_not_make_a_request() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("No request should be made without credentials")

    publisher = TelegramPublisher(
        None, None, transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(publisher.publish(request()))

    assert result.status == "failed"
    assert "credentials" in (result.error or "")


def test_platform_failure_does_not_stop_other_publishers() -> None:
    class BrokenTelegramPublisher:
        platform = Platform.TELEGRAM

        async def publish(self, _: PostingRequest) -> PlatformResult:
            raise RuntimeError("isolated test failure")

    class RecordingLinkedInPublisher:
        platform = Platform.LINKEDIN
        called = False

        async def publish(self, _: PostingRequest) -> PlatformResult:
            self.called = True
            return PlatformResult(
                platform=Platform.LINKEDIN,
                status="failed",
                error="Not configured in this test.",
            )

    linkedin = RecordingLinkedInPublisher()
    service = PostingService(
        target_platforms=[Platform.TELEGRAM, Platform.LINKEDIN],
        publishers={
            Platform.TELEGRAM: BrokenTelegramPublisher(),  # type: ignore[dict-item]
            Platform.LINKEDIN: linkedin,  # type: ignore[dict-item]
        },
    )
    response = asyncio.run(service.publish(request()))

    assert linkedin.called is True
    assert [result.status for result in response.results] == ["failed", "failed"]
