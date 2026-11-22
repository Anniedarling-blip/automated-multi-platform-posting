"""FastAPI application entry point."""

from fastapi import FastAPI

from app.config import get_settings
from app.platforms.bluesky import BlueskyPublisher
from app.platforms.discord import DiscordPublisher
from app.platforms.mastodon import MastodonPublisher
from app.platforms.slack import SlackPublisher
from app.platforms.telegram import TelegramPublisher
from app.schemas import Platform, PostingRequest, PostingResponse
from app.services.posting_service import PostingService

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
telegram_token = (
    settings.telegram_bot_token.get_secret_value()
    if settings.telegram_bot_token
    else None
)
discord_webhook_url = (
    settings.discord_webhook_url.get_secret_value()
    if settings.discord_webhook_url
    else None
)
bluesky_app_password = (
    settings.bluesky_app_password.get_secret_value()
    if settings.bluesky_app_password
    else None
)
mastodon_access_token = (
    settings.mastodon_access_token.get_secret_value()
    if settings.mastodon_access_token
    else None
)
slack_webhook_url = (
    settings.slack_webhook_url.get_secret_value()
    if settings.slack_webhook_url
    else None
)
posting_service = PostingService(
    target_platforms=settings.target_platforms,
    publishers={
        Platform.TELEGRAM: TelegramPublisher(
            bot_token=telegram_token,
            chat_id=settings.telegram_chat_id,
        ),
        Platform.DISCORD: DiscordPublisher(webhook_url=discord_webhook_url),
        Platform.BLUESKY: BlueskyPublisher(
            handle=settings.bluesky_handle,
            app_password=bluesky_app_password,
        ),
        Platform.MASTODON: MastodonPublisher(
            base_url=settings.mastodon_base_url,
            access_token=mastodon_access_token,
        ),
        Platform.SLACK: SlackPublisher(webhook_url=slack_webhook_url),
    },
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Report that the API process is running."""
    return {"status": "ok"}


@app.post("/posting", response_model=PostingResponse)
async def create_post(request: PostingRequest) -> PostingResponse:
    """Publish to configured platforms and report each platform's outcome."""
    return await posting_service.publish(request)

