"""Ежедневная отправка списка дел планирования в Telegram. Изолирована от ClassHub."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

import plan_database
import plan_service

STATE_PATH = os.path.join(plan_database.DATA_DIR, "plan_daily_schedule_state.json")
_scheduler_started = False
_scheduler_lock = threading.Lock()


def _request(url: str, data: bytes, headers: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            description = json.loads(raw).get("description") or f"Ошибка Telegram ({exc.code})"
        except json.JSONDecodeError:
            description = f"Ошибка Telegram ({exc.code})"
        raise plan_service.PlanError(description)
    parsed = json.loads(raw)
    if not parsed.get("ok"):
        raise plan_service.PlanError(parsed.get("description") or "Telegram отклонил запрос")
    return parsed


def send_text(token: str, chat_id: str, text: str) -> int | None:
    if not token or not chat_id:
        raise plan_service.PlanError("Укажите токен бота и chat id")
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": (text or "")[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    parsed = _request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        payload,
        {"Content-Type": "application/json; charset=utf-8"},
    )
    result = parsed.get("result") or {}
    message_id = result.get("message_id")
    return int(message_id) if message_id else None


def delete_message(token: str, chat_id: str, message_id: int) -> bool:
    payload = json.dumps({"chat_id": chat_id, "message_id": message_id}).encode("utf-8")
    try:
        _request(
            f"https://api.telegram.org/bot{token}/deleteMessage",
            payload,
            {"Content-Type": "application/json; charset=utf-8"},
            timeout=20,
        )
        return True
    except plan_service.PlanError:
        return False


def _load_state() -> dict:
    if not os.path.isfile(STATE_PATH):
        return {"messages": {}, "lastSent": None, "lastError": None, "lastAt": None}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {"messages": {}, "lastSent": None, "lastError": None, "lastAt": None}
        data.setdefault("messages", {})
        return data
    except (OSError, json.JSONDecodeError):
        return {"messages": {}, "lastSent": None, "lastError": None, "lastAt": None}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def send_daily_list(test: bool = False) -> dict:
    settings = plan_service.get_settings()
    if not test and not settings.get("dailyScheduleEnabled"):
        raise plan_service.PlanError("Ежедневная отправка списка дел выключена")
    token = (settings.get("telegramBotToken") or "").strip()
    recipients = list(settings.get("chatIds") or [])
    if not token:
        raise plan_service.PlanError("Укажите токен бота")
    if not recipients:
        raise plan_service.PlanError("Укажите chat id")
    html = plan_service.format_today_html()
    state = _load_state()
    messages = dict(state.get("messages") or {})
    errors: list[str] = []
    for chat_id in recipients:
        try:
            new_id = send_text(token, chat_id, html)
        except plan_service.PlanError as exc:
            errors.append(f"{chat_id}: {exc.message}")
            continue
        old_ids = [int(item) for item in messages.get(chat_id, []) if str(item).lstrip("-").isdigit()]
        kept: list[int] = []
        for old_id in old_ids:
            if new_id and old_id == new_id:
                continue
            if not delete_message(token, chat_id, old_id):
                kept.append(old_id)
        if new_id:
            kept.append(new_id)
        messages[chat_id] = kept
    now = datetime.now().isoformat(timespec="seconds")
    state["messages"] = messages
    state["lastAt"] = now
    if errors:
        state["lastError"] = "; ".join(errors)
        _save_state(state)
        if len(errors) == len(recipients):
            raise plan_service.PlanError("Не удалось отправить: " + "; ".join(errors))
        raise plan_service.PlanError("Отправлено частично. Ошибки: " + "; ".join(errors))
    state["lastError"] = None
    if not test:
        state["lastSent"] = datetime.now().date().isoformat()
    _save_state(state)
    return {"ok": True, "test": test, "recipients": len(recipients)}


def status() -> dict:
    state = _load_state()
    return {
        "lastSent": state.get("lastSent"),
        "lastError": state.get("lastError"),
        "lastAt": state.get("lastAt"),
    }


def _tick() -> None:
    try:
        settings = plan_service.get_settings()
    except Exception:
        return
    if not settings.get("dailyScheduleEnabled"):
        return
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute
    target = int(settings.get("dailyScheduleMinutes") or 7 * 60)
    if current_minutes < target:
        return
    state = _load_state()
    if state.get("lastSent") == now.date().isoformat():
        return
    try:
        send_daily_list(test=False)
    except Exception as exc:
        state = _load_state()
        state["lastError"] = str(getattr(exc, "message", None) or exc)
        state["lastAt"] = datetime.now().isoformat(timespec="seconds")
        _save_state(state)


def start_scheduler() -> None:
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    def loop() -> None:
        while True:
            _tick()
            time.sleep(20)

    thread = threading.Thread(target=loop, name="plan-daily-schedule", daemon=True)
    thread.start()
