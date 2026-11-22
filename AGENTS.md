
# Repository Guidelines

## Project Overview

This repository contains an Automated Multi-Platform Posting System built using Python and FastAPI.

The application accepts a message through a REST API and independently publishes it to configured third-party platforms.

## Project Structure

- `app/main.py` – FastAPI application and API endpoint.
- `app/schemas.py` – Request and response validation.
- `app/config.py` – Application configuration and environment variables.
- `app/platforms/` – Individual platform integrations.
- `app/services/posting_service.py` – Posting orchestration.
- `tests/` – Automated tests for API functionality and platform integrations.
- `.env.example` – Example environment configuration.
- `requirements.txt` – Python dependencies.

## Development Commands

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the application:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 4000
```

Open API documentation:

`http://localhost:4000/docs`

Run tests:

```bash
python -m pytest -q
```

## Coding Guidelines

- Use Python conventions and PEP 8.
- Keep each platform integration independent.
- Use HTTPX for HTTP API requests.
- Use Pydantic for request and response validation.
- Keep configuration separate from application logic.
- Handle API errors without interrupting other platform integrations.

## Testing Guidelines

- Add tests for new functionality.
- Test validation and error-handling scenarios.
- Test individual platform adapters independently.
- Run the complete test suite before committing changes.

## Security

- Store credentials in environment variables.
- Never commit `.env` files or API credentials.
- Keep `.env.example` limited to placeholder values.
- Never expose tokens, passwords, or webhook URLs in logs or screenshots.

## Git Guidelines

- Use descriptive commit messages.
- Keep commits focused on individual changes.
- Verify tests before pushing changes to GitHub.
