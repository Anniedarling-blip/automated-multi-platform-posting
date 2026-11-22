"""Request validation and no-fake-publishing tests."""

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.platforms.telegram import TelegramPublisher
from app.schemas import Platform, PlatformResult, PostingRequest, extract_cta_url
from app.services.posting_service import PostingService

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_posting_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep API validation tests isolated from any real Telegram account."""

    def telegram_api(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "message_id": 42,
                    "date": 1_700_000_000,
                    "chat": {
                        "id": -100123,
                        "type": "channel",
                        "username": "test_channel",
                    },
                },
            },
        )

    mocked_service = PostingService(
        target_platforms=[Platform.TELEGRAM],
        publishers={
            Platform.TELEGRAM: TelegramPublisher(
                "test-token",
                "@test_channel",
                transport=httpx.MockTransport(telegram_api),
            )
        },
    )
    monkeypatch.setattr(main_module, "posting_service", mocked_service)


def valid_payload() -> dict[str, str]:
    return {
        "message": "Check out our latest business platform. https://example.com",
    }


def test_accepts_exact_request_format_with_mocked_telegram_confirmation() -> None:
    payload = valid_payload()

    assert set(PostingRequest.model_fields) == {"message"}
    response = client.post("/posting", json=payload)

    assert response.status_code == 200
    assert response.json()["results"][0]["platform"] == "telegram"
    assert response.json()["results"][0]["status"] == "posted"


def test_rejects_empty_or_whitespace_message() -> None:
    for message in ("", "   ", "\n\t"):
        response = client.post("/posting", json={"message": message})
        assert response.status_code == 422


def test_accepts_message_at_200_characters() -> None:
    message = "https://example.com " + "x" * 180
    assert len(message) == 200

    response = client.post("/posting", json={"message": message})

    assert response.status_code == 200


def test_rejects_message_over_200_characters() -> None:
    message = "https://example.com " + "x" * 181

    response = client.post("/posting", json={"message": message})

    assert response.status_code == 422


def test_accepts_http_and_https_urls() -> None:
    assert extract_cta_url("Visit http://example.com") == "http://example.com"
    assert extract_cta_url("Visit https://example.com") == "https://example.com"


def test_rejects_message_with_zero_urls() -> None:
    response = client.post(
        "/posting",
        json={"message": "Check out our latest business platform."},
    )

    assert response.status_code == 422


def test_rejects_message_with_multiple_urls() -> None:
    response = client.post(
        "/posting",
        json={"message": "https://example.com and http://example.org"},
    )

    assert response.status_code == 422


def test_rejects_url_without_hostname() -> None:
    for url in ("http://", "https://?query=value", "https:///path"):
        response = client.post("/posting", json={"message": f"See {url}"})
        assert response.status_code == 422


def test_rejects_invalid_hostname_or_port() -> None:
    for url in ("https://bad_host.example", "https://example.com:99999"):
        response = client.post("/posting", json={"message": f"See {url}"})
        assert response.status_code == 422


def test_rejects_message_with_only_non_http_url() -> None:
    response = client.post(
        "/posting",
        json={"message": "Download ftp://example.org/file"},
    )

    assert response.status_code == 422


def test_rejects_legacy_public_fields_and_other_extra_fields() -> None:
    payload = valid_payload()
    payload["cta_url"] = "https://example.com"
    payload["platforms"] = "linkedin"
    payload["extra"] = "value"

    response = client.post("/posting", json=payload)

    assert response.status_code == 422


def test_response_result_has_all_assessment_fields() -> None:
    assert set(PlatformResult.model_fields) == {
        "platform",
        "status",
        "posted_url",
        "public_access",
        "date",
        "time",
        "error",
    }
