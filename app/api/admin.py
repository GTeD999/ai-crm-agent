from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from app.core.config import settings
from app.db.client import get_supabase
from app.db.repositories.settings import SettingsRepository
from app.db.table_names import AI_EVENTS_TABLE, AI_LEADS_TABLE, AI_MESSAGES_TABLE, AI_USERS_TABLE
from app.services.properties.sync import QuickDealSyncService

router = APIRouter(prefix="/admin", tags=["admin"])
security = HTTPBasic()


class ToggleRequest(BaseModel):
    enabled: bool


class QuickDealSettingsRequest(BaseModel):
    feed_url: str


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    expected_password = settings.admin_password
    if not expected_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin password is not configured",
        )
    username_ok = secrets.compare_digest(credentials.username, settings.admin_username)
    password_ok = secrets.compare_digest(credentials.password, expected_password)
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_page(_: str = Depends(require_admin)) -> HTMLResponse:
    return HTMLResponse(ADMIN_HTML)


@router.get("/api/bootstrap")
async def bootstrap(_: str = Depends(require_admin)) -> dict[str, Any]:
    client = await get_supabase()
    settings_repo = SettingsRepository()
    ai_enabled = await settings_repo.get_bool("ai_enabled", True)
    quickdeal_feed_url = await settings_repo.get_str("quickdeal_feed_url")

    users_response = (
        await client.table(AI_USERS_TABLE)
        .select("*")
        .order("last_message_at", desc=True)
        .limit(50)
        .execute()
    )
    leads_response = (
        await client.table(AI_LEADS_TABLE)
        .select("*")
        .order("updated_at", desc=True)
        .limit(50)
        .execute()
    )
    events_response = (
        await client.table(AI_EVENTS_TABLE)
        .select("*")
        .order("created_at", desc=True)
        .limit(80)
        .execute()
    )
    messages_response = (
        await client.table(AI_MESSAGES_TABLE)
        .select("id,user_id,role,content,tokens_input,tokens_output,model,created_at")
        .order("created_at", desc=True)
        .limit(300)
        .execute()
    )

    users = users_response.data or []
    leads = leads_response.data or []
    events = events_response.data or []
    messages = messages_response.data or []
    user_map = {row["id"]: row for row in users}
    cost = calculate_openai_cost(messages)

    chats = []
    for user in users:
        user_messages = [message for message in messages if message.get("user_id") == user["id"]]
        last_message = user_messages[0] if user_messages else None
        chats.append(
            {
                "id": user["id"],
                "name": " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or "Без имени",
                "telegram": f"@{user.get('telegram_username')}" if user.get("telegram_username") else "",
                "telegram_id": user.get("telegram_id"),
                "phone": user.get("phone"),
                "pd_consent": user.get("pd_consent"),
                "is_silent": user.get("is_silent"),
                "last_message_at": user.get("last_message_at"),
                "last_message": trim(last_message.get("content", ""), 160) if last_message else "",
                "messages_loaded": len(user_messages),
            }
        )

    return {
        "settings": {
            "ai_enabled": ai_enabled,
            "telegram_enabled": settings.telegram_enabled,
            "quickdeal_feed_url": quickdeal_feed_url or settings.quickdeal_feed_url or "",
            "quickdeal_sync_interval_minutes": settings.quickdeal_sync_interval_minutes,
        },
        "metrics": {
            "users_loaded": len(users),
            "leads_loaded": len(leads),
            "messages_loaded": len(messages),
            "events_loaded": len(events),
            "openai": cost,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "chats": chats,
        "leads": [format_lead(row, user_map.get(row.get("user_id"))) for row in leads],
        "events": events,
    }


@router.get("/api/chats/{user_id}")
async def chat_detail(user_id: UUID, _: str = Depends(require_admin)) -> dict[str, Any]:
    client = await get_supabase()
    user_response = await client.table(AI_USERS_TABLE).select("*").eq("id", str(user_id)).limit(1).execute()
    messages_response = (
        await client.table(AI_MESSAGES_TABLE)
        .select("*")
        .eq("user_id", str(user_id))
        .order("created_at", desc=False)
        .limit(200)
        .execute()
    )
    leads_response = (
        await client.table(AI_LEADS_TABLE)
        .select("*")
        .eq("user_id", str(user_id))
        .order("updated_at", desc=True)
        .limit(10)
        .execute()
    )
    return {
        "user": (user_response.data or [None])[0],
        "messages": messages_response.data or [],
        "leads": leads_response.data or [],
        "openai": calculate_openai_cost(messages_response.data or []),
    }


@router.post("/api/settings/ai-enabled")
async def set_ai_enabled(payload: ToggleRequest, _: str = Depends(require_admin)) -> dict[str, bool]:
    await SettingsRepository().set_bool("ai_enabled", payload.enabled)
    return {"ai_enabled": payload.enabled}


@router.post("/api/settings/quickdeal")
async def set_quickdeal_settings(
    payload: QuickDealSettingsRequest, _: str = Depends(require_admin)
) -> dict[str, str]:
    feed_url = payload.feed_url.strip()
    if feed_url and not feed_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Feed URL must start with http:// or https://")
    await SettingsRepository().set_str("quickdeal_feed_url", feed_url)
    return {"quickdeal_feed_url": feed_url}


@router.post("/api/properties/sync")
async def sync_properties(_: str = Depends(require_admin)) -> dict[str, Any]:
    count = await QuickDealSyncService().sync()
    return {"ok": True, "synced": count, "synced_at": datetime.now(timezone.utc).isoformat()}


def calculate_openai_cost(messages: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, dict[str, float]] = {}
    for message in messages:
        model = message.get("model") or "unknown"
        input_tokens = int(message.get("tokens_input") or 0)
        output_tokens = int(message.get("tokens_output") or 0)
        if not input_tokens and not output_tokens:
            continue
        row = by_model.setdefault(model, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
        row["input_tokens"] += input_tokens
        row["output_tokens"] += output_tokens
        row["cost_usd"] += estimate_cost(model, input_tokens, output_tokens)
    total = sum(row["cost_usd"] for row in by_model.values())
    return {
        "by_model": by_model,
        "total_usd": round(total, 6),
        "total_rub_approx": round(total * 95, 2),
        "note": "Расчет приблизительный по сохраненным token usage в ai_manager_messages.",
    }


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if "mini" in model:
        input_rate = settings.openai_fast_input_usd_per_1m
        output_rate = settings.openai_fast_output_usd_per_1m
    else:
        input_rate = settings.openai_main_input_usd_per_1m
        output_rate = settings.openai_main_output_usd_per_1m
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


def format_lead(lead: dict[str, Any], user: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": lead.get("id"),
        "client": " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) if user else "Без имени",
        "telegram": f"@{user.get('telegram_username')}" if user and user.get("telegram_username") else "",
        "phone": user.get("phone") if user else "",
        "status": lead.get("status"),
        "reason": lead.get("transfer_reason"),
        "bitrix_lead_id": lead.get("bitrix_lead_id"),
        "property_type": lead.get("property_type"),
        "deal_type": lead.get("deal_type"),
        "budget": format_budget(lead.get("price_min"), lead.get("price_max")),
        "city": lead.get("city"),
        "updated_at": lead.get("updated_at"),
        "notes": trim(lead.get("additional_notes") or "", 220),
    }


def format_budget(price_min: int | None, price_max: int | None) -> str:
    if price_min and price_max:
        return f"{price_min:,} - {price_max:,}".replace(",", " ") + " руб."
    if price_max:
        return f"до {price_max:,}".replace(",", " ") + " руб."
    if price_min:
        return f"от {price_min:,}".replace(",", " ") + " руб."
    return ""


def trim(value: str, limit: int) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


ADMIN_HTML = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Novactive AI Manager</title>
  <style>
    :root { color-scheme: light; --bg:#f6f7f9; --panel:#fff; --text:#18202a; --muted:#667085; --line:#d9dee7; --accent:#0f766e; --bad:#b42318; }
    * { box-sizing: border-box; }
    body { margin:0; font:14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; background:var(--bg); color:var(--text); }
    header { display:flex; justify-content:space-between; gap:16px; align-items:center; padding:18px 24px; background:#101828; color:#fff; }
    h1 { margin:0; font-size:20px; }
    main { padding:20px 24px 40px; }
    .grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin-bottom:16px; }
    .card, .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; }
    .card { padding:14px; }
    .card b { display:block; font-size:22px; margin-top:6px; }
    .muted { color:var(--muted); }
    .tabs { display:flex; gap:8px; margin:16px 0; }
    button { border:1px solid var(--line); background:#fff; color:var(--text); padding:9px 12px; border-radius:6px; cursor:pointer; font-weight:600; }
    button.active { background:#101828; color:#fff; border-color:#101828; }
    button.danger { background:var(--bad); color:#fff; border-color:var(--bad); }
    button.good { background:var(--accent); color:#fff; border-color:var(--accent); }
    table { width:100%; border-collapse:collapse; }
    th, td { text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; }
    th { font-size:12px; color:var(--muted); background:#fbfcfe; position:sticky; top:0; }
    .panel { overflow:auto; max-height:65vh; }
    .rowbtn { color:#0f5fbb; text-decoration:underline; cursor:pointer; }
    .chat { display:grid; gap:10px; }
    .msg { padding:10px 12px; border-radius:8px; max-width:860px; white-space:pre-wrap; border:1px solid var(--line); background:#fff; }
    .msg.user { margin-left:auto; background:#eef8f6; border-color:#c7ebe5; }
    .msg.assistant { background:#fff; }
    .msg.tool { background:#f5f5f5; color:#667085; font-size:12px; }
    .hidden { display:none; }
    @media (max-width: 900px) { .grid { grid-template-columns:1fr 1fr; } header { align-items:flex-start; flex-direction:column; } }
  </style>
</head>
<body>
  <header>
    <div><h1>Novactive AI Manager</h1><div class="muted">Telegram, Bitrix, лиды и расходы OpenAI</div></div>
    <div><button id="aiToggle">Загрузка...</button></div>
  </header>
  <main>
    <section class="grid">
      <div class="card"><span class="muted">Чаты</span><b id="mUsers">0</b></div>
      <div class="card"><span class="muted">Лиды</span><b id="mLeads">0</b></div>
      <div class="card"><span class="muted">Сообщения</span><b id="mMessages">0</b></div>
      <div class="card"><span class="muted">OpenAI</span><b id="mCost">$0</b><span id="mCostRub" class="muted"></span></div>
    </section>
    <nav class="tabs">
      <button class="active" data-tab="chats">Чаты</button>
      <button data-tab="leads">Лиды</button>
      <button data-tab="events">События</button>
      <button data-tab="costs">API расходы</button>
      <button data-tab="settings">Настройки</button>
    </nav>
    <section id="tab-chats" class="panel"></section>
    <section id="tab-leads" class="panel hidden"></section>
    <section id="tab-events" class="panel hidden"></section>
    <section id="tab-costs" class="panel hidden"></section>
    <section id="tab-settings" class="panel hidden"></section>
  </main>
<script>
let state = null;
const adminBase = location.pathname.replace(/\\/$/, '');
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[s]));
async function load() {
  const res = await fetch(adminBase + '/api/bootstrap');
  state = await res.json();
  render();
}
function render() {
  document.getElementById('mUsers').textContent = state.metrics.users_loaded;
  document.getElementById('mLeads').textContent = state.leads.length;
  document.getElementById('mMessages').textContent = state.metrics.messages_loaded;
  document.getElementById('mCost').textContent = '$' + state.metrics.openai.total_usd.toFixed(4);
  document.getElementById('mCostRub').textContent = '≈ ' + state.metrics.openai.total_rub_approx + ' ₽';
  const toggle = document.getElementById('aiToggle');
  toggle.textContent = state.settings.ai_enabled ? 'AI включен' : 'AI выключен';
  toggle.className = state.settings.ai_enabled ? 'good' : 'danger';
  renderChats(); renderLeads(); renderEvents(); renderCosts(); renderSettings();
}
function renderChats() {
  document.getElementById('tab-chats').innerHTML = `<table><thead><tr><th>Клиент</th><th>Telegram</th><th>Телефон</th><th>Состояние</th><th>Последнее</th><th></th></tr></thead><tbody>${state.chats.map(c => `<tr><td><b>${esc(c.name)}</b><br><span class="muted">${esc(c.last_message_at)}</span></td><td>${esc(c.telegram)}<br><span class="muted">${esc(c.telegram_id)}</span></td><td>${esc(c.phone || '')}</td><td>${c.is_silent ? 'передан менеджеру' : 'AI активен'}<br>${c.pd_consent ? 'ПД: да' : 'ПД: нет'}</td><td>${esc(c.last_message)}</td><td><span class="rowbtn" onclick="openChat('${c.id}')">открыть</span></td></tr>`).join('')}</tbody></table>`;
}
function renderLeads() {
  document.getElementById('tab-leads').innerHTML = `<table><thead><tr><th>Клиент</th><th>Статус</th><th>Запрос</th><th>Bitrix</th><th>Заметка</th></tr></thead><tbody>${state.leads.map(l => `<tr><td><b>${esc(l.client)}</b><br>${esc(l.telegram)}<br>${esc(l.phone || '')}</td><td>${esc(l.status)}<br><span class="muted">${esc(l.reason || '')}</span></td><td>${esc([l.deal_type,l.property_type,l.city,l.budget].filter(Boolean).join(', '))}</td><td>${esc(l.bitrix_lead_id || '')}</td><td>${esc(l.notes || '')}</td></tr>`).join('')}</tbody></table>`;
}
function renderEvents() {
  document.getElementById('tab-events').innerHTML = `<table><thead><tr><th>Время</th><th>Тип</th><th>Данные</th></tr></thead><tbody>${state.events.map(e => `<tr><td>${esc(e.created_at)}</td><td>${esc(e.event_type)}</td><td><pre>${esc(JSON.stringify(e.event_data || {}, null, 2))}</pre></td></tr>`).join('')}</tbody></table>`;
}
function renderCosts() {
  const rows = Object.entries(state.metrics.openai.by_model).map(([model, row]) => `<tr><td>${esc(model)}</td><td>${row.input_tokens}</td><td>${row.output_tokens}</td><td>$${row.cost_usd.toFixed(6)}</td></tr>`).join('');
  document.getElementById('tab-costs').innerHTML = `<div class="card"><b>$${state.metrics.openai.total_usd.toFixed(6)} / ≈ ${state.metrics.openai.total_rub_approx} ₽</b><p class="muted">${esc(state.metrics.openai.note)}</p></div><table><thead><tr><th>Модель</th><th>Input tokens</th><th>Output tokens</th><th>Стоимость</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function renderSettings() {
  document.getElementById('tab-settings').innerHTML = `
    <div class="card">
      <h2>QuickDeal XML</h2>
      <p class="muted">Источник объектов для подбора. Автосинхронизация: каждые ${esc(state.settings.quickdeal_sync_interval_minutes)} мин.</p>
      <label class="muted" for="quickdealUrl">XML URL</label>
      <input id="quickdealUrl" value="${esc(state.settings.quickdeal_feed_url || '')}" placeholder="https://quick-deal.ru/api/..." style="width:100%; margin:6px 0 12px; padding:10px 12px; border:1px solid var(--line); border-radius:6px;">
      <button class="good" onclick="saveQuickDeal()">Сохранить</button>
      <button onclick="syncQuickDeal()">Синхронизировать сейчас</button>
      <span id="quickdealStatus" class="muted"></span>
    </div>`;
}
async function saveQuickDeal() {
  const feed_url = document.getElementById('quickdealUrl').value.trim();
  const status = document.getElementById('quickdealStatus');
  status.textContent = 'Сохраняю...';
  const res = await fetch(adminBase + '/api/settings/quickdeal', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({feed_url})});
  if (!res.ok) {
    status.textContent = 'Ошибка сохранения';
    return;
  }
  status.textContent = 'Сохранено';
  await load();
}
async function syncQuickDeal() {
  const status = document.getElementById('quickdealStatus');
  status.textContent = 'Синхронизация...';
  const res = await fetch(adminBase + '/api/properties/sync', {method:'POST'});
  if (!res.ok) {
    status.textContent = 'Ошибка синхронизации';
    return;
  }
  const data = await res.json();
  status.textContent = `Загружено: ${data.synced}`;
}
async function openChat(id) {
  const res = await fetch(adminBase + '/api/chats/' + id);
  const data = await res.json();
  document.getElementById('tab-chats').innerHTML = `<div class="card"><button onclick="renderChats()">Назад</button> <b>${esc((data.user?.first_name || '') + ' ' + (data.user?.last_name || ''))}</b> <span class="muted">@${esc(data.user?.telegram_username || '')}</span></div><div class="chat">${data.messages.map(m => `<div class="msg ${esc(m.role)}"><b>${esc(m.role)}</b><br>${esc(m.content)}</div>`).join('')}</div>`;
}
document.querySelectorAll('[data-tab]').forEach(btn => btn.onclick = () => {
  document.querySelectorAll('[data-tab]').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  ['chats','leads','events','costs','settings'].forEach(t => document.getElementById('tab-' + t).classList.toggle('hidden', t !== btn.dataset.tab));
});
document.getElementById('aiToggle').onclick = async () => {
  const enabled = !state.settings.ai_enabled;
  await fetch(adminBase + '/api/settings/ai-enabled', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({enabled})});
  await load();
};
load();
</script>
</body>
</html>
"""
