# Automated Multi-Platform Posting System

A FastAPI application that accepts one short message and publishes it
independently to five third-party platforms: **Telegram, Discord,
Bluesky, Mastodon, and Slack**.

The application exposes a single REST endpoint:

`POST /posting`

Platform selection is handled internally through environment
configuration. A failure on one platform does not prevent attempts on
the others.

## Features

-   FastAPI REST API with interactive Swagger documentation.
-   Pydantic request validation.
-   Message length limited to 200 characters.
-   Exactly one valid CTA URL required in each message.
-   Five independent platform adapters:
    -   Telegram Bot API
    -   Discord Webhooks
    -   Bluesky API
    -   Mastodon API
    -   Slack Incoming Webhooks
-   Per-platform result reporting, including status, post URL when
    available, public-access information when available, date/time, and
    error details.
-   Credentials loaded from environment variables.
-   Automated tests for request validation, posting orchestration, and
    platform adapters.

## Technology Stack

-   Python 3.x
-   FastAPI
-   Uvicorn
-   Pydantic
-   HTTPX
-   pytest
-   python-dotenv (if used by the project configuration)

## Project Structure

``` text
automated-posting/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── platforms/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── telegram.py
│   │   ├── discord.py
│   │   ├── bluesky.py
│   │   ├── mastodon.py
│   │   └── slack.py
│   └── services/
│       ├── __init__.py
│       └── posting_service.py
├── tests/
│   ├── __init__.py
│   ├── test_posting.py
│   ├── test_telegram.py
│   ├── test_discord.py
│   ├── test_bluesky.py
│   ├── test_mastodon.py
│   └── test_slack.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Requirements

-   Python 3.10 or later is recommended.
-   API credentials/configuration for the platforms you want to enable.
-   Internet access for outbound API requests.

## Installation

### 1. Clone the repository

``` bash
git clone https://github.com/Anniedarling-blip/automated-multi-platform-posting.git
cd automated-multi-platform-posting
```

### 2. Create and activate a virtual environment

**Windows PowerShell**

``` powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux**

``` bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

``` bash
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file in the project root by copying
`.env.example`:

**Windows PowerShell**

``` powershell
Copy-Item .env.example .env
```

**macOS / Linux**

``` bash
cp .env.example .env
```

Fill in the required values using the variable names documented in
`.env.example` and read by `app/config.py`. Configure only the platforms
you intend to enable.

Typical credentials/configuration include:

  Platform      Required configuration
  ------------- ----------------------------------------
  Telegram      Bot token and destination chat/channel
  Discord       Webhook URL
  Bluesky       Account identifier and app password
  Mastodon      Instance URL and access token
  Slack         Incoming webhook URL
  Application   Enabled target platforms

**Security:** Never commit `.env`, API tokens, passwords, or webhook
URLs. The repository should contain `.env.example` with placeholders
only. If a credential has ever been exposed publicly, revoke or rotate
it.

## Run the Application

Start the API from the repository root:

``` bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 4000
```

The API will be available at:

-   Base URL: `http://localhost:4000`
-   Posting endpoint: `http://localhost:4000/posting`
-   Swagger UI: `http://localhost:4000/docs`

## API Usage

### Endpoint

``` http
POST /posting
Content-Type: application/json
```

### Request body

``` json
{
  "message": "Check out our latest business platform and grow your online visibility. https://example.com"
}
```

### Validation rules

-   `message` must not exceed 200 characters.
-   The message must contain exactly one CTA link.
-   The URL must be valid.
-   The client does not choose the target platforms; the application
    selects enabled platforms from its configuration.

Invalid requests should return an appropriate HTTP validation response.

### Example request using cURL

``` bash
curl -X POST "http://localhost:4000/posting" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Check out our latest business platform and grow your online visibility. https://example.com\"}"
```

### Example response shape

The following is an **illustrative response shape only**. Actual status,
URLs, timestamps, and errors depend on the live API responses from the
connected platform accounts.

``` json
{
  "success": true,
  "results": [
    {
      "platform": "telegram",
      "status": "success",
      "posted_url": "https://t.me/your_channel/123",
      "public_access": true,
      "date": "2026-11-22",
      "time": "10:30:00",
      "error": null
    },
    {
      "platform": "discord",
      "status": "failed",
      "posted_url": null,
      "public_access": null,
      "date": null,
      "time": null,
      "error": "Example API error; see the actual response for details."
    }
  ]
}
```

A platform may not provide a permalink or enough information to
determine public visibility. In those cases, the corresponding fields
may be `null`; the application should not invent a URL or claim public
access without evidence.

## Platform Integrations

  -----------------------------------------------------------------------
  Platform                Integration method      Notes
  ----------------------- ----------------------- -----------------------
  Telegram                Telegram Bot API        Sends a message to the
                                                  configured
                                                  chat/channel.

  Discord                 Discord Execute Webhook Publishes through the
                                                  configured webhook.

  Bluesky                 Bluesky API             Authenticates and
                                                  creates a post record.

  Mastodon                Mastodon REST API       Publishes a status to
                                                  the configured
                                                  instance.

  Slack                   Slack Incoming Webhook  Sends a message to the
                                                  configured Slack
                                                  destination.
  -----------------------------------------------------------------------

Each platform is handled independently. A failure from one platform
should be captured in that platform's result without stopping the
remaining posting attempts.

## Testing

Run the automated test suite from the project root:

``` bash
python -m pytest -q
```

The project test suite previously completed with **112 passed**. This is
a test-suite result, not proof that every external platform is currently
reachable. Live integration checks require valid credentials and
successful API responses from each provider.

## Evidence for Review

For the practical-test submission, include genuine screenshots or logs
showing:

1.  The FastAPI Swagger page at `/docs`.
2.  A valid request submitted to `/posting`.
3.  The API response showing per-platform results.
4.  The corresponding messages/posts in the enabled platform
    destinations.
5.  A validation example for an invalid request.

Do not include credentials, authorization headers, bot tokens, app
passwords, or webhook URLs in screenshots or logs.

## Design Notes

-   **Separation of concerns:** API routing, request/response schemas,
    platform adapters, and posting orchestration are separated into
    modules.
-   **Independent execution:** Each platform integration reports its own
    outcome so one failure does not block other platforms.
-   **Configuration:** Target platforms and credentials are supplied
    through environment configuration rather than request-body platform
    selection.
-   **Validation:** Input is validated before posting is attempted.

## API Documentation and References

Official platform API documentation:

-   [Telegram Bot API](https://core.telegram.org/bots/api)
-   [Discord
    Webhooks](https://discord.com/developers/docs/resources/webhook)
-   [Bluesky API documentation](https://docs.bsky.app/)
-   [Mastodon API documentation](https://docs.joinmastodon.org/)
-   [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)

## Repository

[GitHub --
automated-multi-platform-posting](https://github.com/Anniedarling-blip/automated-multi-platform-posting)
