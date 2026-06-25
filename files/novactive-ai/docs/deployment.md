# Деплой

## Локальная разработка

```bash
# 1. Клонировать репозиторий
git clone <repo> officee-bot && cd officee-bot

# 2. Создать виртуальное окружение
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Скопировать env
cp .env.example .env
# Заполнить все ключи

# 4. Накатить миграцию в Supabase
# Открыть SQL Editor в Supabase Dashboard, скопировать содержимое schemas/database.sql, выполнить

# 5. Загрузить объекты в БД
python scripts/seed_properties.py --file=data/properties.csv

# 6. Загрузить базу знаний
python scripts/seed_knowledge.py --file=data/knowledge.csv

# 7. Сгенерировать эмбеддинги
python scripts/generate_embeddings.py

# 8. Для локальной разработки использовать polling вместо webhook
APP_ENV=development python -m app.main
```

В режиме development бот работает в polling режиме — не нужен публичный URL.

## Продакшен (VPS + Docker)

### Требования к серверу

- Ubuntu 22.04+
- 2 vCPU, 2 GB RAM минимум (для MVP)
- Docker + Docker Compose
- Доменное имя с SSL (для Telegram webhook)
- Открытые порты: 80, 443

### Деплой

```bash
# На сервере
git clone <repo> /opt/officee-bot
cd /opt/officee-bot
cp .env.example .env
nano .env  # заполнить

# Запуск
docker compose up -d

# Установка webhook в Telegram
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -d "url=https://bot.officee.ru/api/telegram/webhook&secret_token=$TELEGRAM_WEBHOOK_SECRET"
```

### docker-compose.yml

```yaml
version: "3.9"

services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
    expose:
      - "8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config

volumes:
  caddy_data:
  caddy_config:
```

### Caddyfile

```
bot.officee.ru {
    reverse_proxy bot:8000
}
```

Caddy автоматически получит SSL-сертификат от Let's Encrypt.

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY app/ ./app/
COPY prompts/ ./prompts/
COPY schemas/ ./schemas/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

## Мониторинг

### Логи

structlog в JSON формате пишет в stdout. Docker собирает в `docker logs`.

Для продакшена подключить:
- **Sentry** для exceptions (`sentry-sdk[fastapi]`)
- **Grafana Loki** или **ELK** для централизованных логов
- **Healthcheck endpoint** мониторится через UptimeRobot или аналог

### Метрики для отслеживания

Логируйте в таблицу `events`:
- `message_received` — сколько сообщений в день
- `lead_qualified` — лидов в день
- `transferred_to_manager` — передач менеджеру
- `viewing_booked` — записей на просмотр
- `openai_tokens_used` — расход по моделям
- `bitrix_sync_failed` — отказы интеграции

### Дашборд

Можно сделать простую страницу `/admin/stats` (за basic auth) с SQL-запросами к `events` для:
- Конверсия: сообщение → лид → передача → просмотр
- Средняя длина диалога до hand-off
- Топ-причин передачи менеджеру
- Расходы на OpenAI в день/неделю

## Резервное копирование

Supabase делает автобэкапы на платных планах. Дополнительно:
- Раз в день экспорт `users`, `messages`, `leads`, `events` в S3-совместимое хранилище
- Хранение 30 дней

## Чек-лист перед запуском

- [ ] Все env заполнены (особенно ключи)
- [ ] Накачена миграция БД
- [ ] Загружены объекты с эмбеддингами
- [ ] Загружена база знаний (ипотека, ЖК, FAQ)
- [ ] В Битрикс созданы кастомные поля
- [ ] Webhook Битрикс настроен
- [ ] Telegram webhook установлен
- [ ] SSL сертификат работает
- [ ] Healthcheck отвечает 200
- [ ] Тестовый диалог прошёл успешно (квалификация + поиск + передача)
- [ ] Sentry подключён
- [ ] Бэкапы настроены
- [ ] Менеджеры обучены принимать лиды от бота
- [ ] На сайте/визитках добавлена ссылка на бота
