# Novactiv AI Manager

AI-powered real estate agency manager — handles client conversations via Telegram, classifies intents, searches properties, and integrates with Bitrix24 CRM.

## Features

- Telegram bot with webhook support
- Dialog engine with conversation memory
- Intent classification (greeting, property request, legal, complaint)
- Property search service with tool calling
- Bitrix24 CRM integration (lead transfer, silent mode)
- OpenAI-powered chat with up to 5 tool iterations
- Follow-up scheduler skeleton

## Tech stack

| Layer | Technology |
|-------|-----------|
| Bot | aiogram 3.x |
| API | FastAPI (Python 3.11+) |
| AI | OpenAI API |
| Database | Supabase |
| CRM | Bitrix24 webhooks |

## Getting started

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Security

Source code only — no API keys, Telegram tokens, or client data included.

## License

Private / portfolio project.
