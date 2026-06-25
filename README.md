# AI CRM Agent

An **AI-powered conversational agent** for client communication over Telegram — classifies intent, maintains dialog state, searches a property catalog, creates CRM leads, and schedules follow-ups. Built as a production-style FastAPI service with optional webhook or polling modes.

## Highlights

- **Telegram bot** — aiogram 3 handlers with FSM-friendly message flow  
- **OpenAI tool calling** — property search, lead extraction, handoff to managers  
- **Explicit dialog state** — deterministic state machine under the LLM layer (no “lost context” between turns)  
- **CRM integration** — Bitrix24 incoming webhooks and deal creation  
- **Property sync** — feed ingestion, embeddings, scheduled refresh  
- **Follow-up scheduler** — APScheduler jobs for multi-step nurture sequences  
- **Admin API** — health, settings, manual triggers  
- **Rate limiting** — per-user message caps  

## How it works

```
Telegram user
     │
     ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ aiogram bot │────►│ DialogEngine │────►│ OpenAI tools │
└─────────────┘     │ + classifier │     │ search · CRM │
                    └──────┬───────┘     └─────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        Supabase      Bitrix24     Follow-up jobs
        (messages,    (deals,      (24h / 3d / 7d)
         leads,        webhooks)
         properties)
```

### Conversation modes

The agent supports buyer / seller / analyst / copywriter style flows with stages: greeting → qualifying → search → handoff. Intent classification and slot extraction feed structured lead records before CRM sync.

### Property catalog

- Sync from external XML/JSON feeds (`QUICKDEAL_FEED_URL`)  
- Batch embedding for semantic search  
- City, price, and type filters exposed as LLM tools  

## Tech stack

| Layer | Technology |
|-------|------------|
| API | FastAPI, Uvicorn |
| Bot | aiogram 3 |
| AI | OpenAI GPT-4o / 4o-mini, function calling, embeddings |
| Database | Supabase (PostgreSQL) |
| CRM | Bitrix24 REST webhooks |
| Scheduler | APScheduler |
| Language | Python 3.11+ |

## Project structure

```
app/
  main.py                 FastAPI app + lifespan (bot polling, scheduler)
  api/                    REST: health, admin, telegram webhook, bitrix webhook
  bot/handlers/           /start, message routing
  services/
    ai/                   classifier, extractor, dialog engine, prompts, tools
    crm/                  Bitrix client
    properties/           sync, search, quickdeal feed
    scheduler/            follow-up jobs
    transfer/             manager handoff logic
  db/                     SQLAlchemy-style repos, migrations via Supabase
schemas/                  OpenAI tool JSON schemas
files/                    Integration notes & example endpoints
```

## Getting started

### Prerequisites

- Python 3.11+
- Supabase project (or local Postgres with compatible schema)
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- OpenAI API key

### Install

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Run modes

| Mode | Env flags |
|------|-----------|
| API only | `TELEGRAM_ENABLED=false` |
| Webhook | `TELEGRAM_ENABLED=true`, set `APP_BASE_URL` + `TELEGRAM_WEBHOOK_SECRET` |
| Long polling (dev) | `TELEGRAM_POLLING_ENABLED=true` |

Register webhook:

```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d "url=https://your-domain.com/api/telegram/webhook"
```

## Configuration

See `.env.example` for the full list. Important groups:

| Group | Variables |
|-------|-----------|
| App | `APP_HOST`, `APP_PORT`, `APP_BASE_URL`, `LOG_LEVEL` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, polling flags |
| OpenAI | `OPENAI_API_KEY`, model names, token cost tracking |
| Supabase | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_DB_URL` |
| Bitrix | `BITRIX_WEBHOOK_URL`, category IDs, urgency routing |
| Agency | `AGENCY_NAME`, `AGENCY_CITY`, work hours, premium thresholds |
| Properties | `QUICKDEAL_FEED_URL`, sync interval, site base URL |
| Follow-ups | `FOLLOWUP_STEP_*` hours/days |
| Admin | `ADMIN_USERNAME`, `ADMIN_PASSWORD` |

## API endpoints (overview)

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness check |
| `POST /api/telegram/webhook` | Telegram updates |
| `POST /api/bitrix/webhook` | CRM events |
| `POST /api/admin/*` | Protected admin operations |

## Security

- **No API keys or client data** in the repository (`key.md` is gitignored)  
- Use separate staging bots and CRM sandboxes for development  
- Configure `RATE_LIMIT_*` to mitigate abuse  
- Validate `BITRIX_INCOMING_WEBHOOK_SECRET` on CRM callbacks  

## License

Portfolio / demonstration project.
