"""Ежедневная отправка списка дел планирования в Telegram. Изолирована от ClassHub."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

import job_lock
import plan_database
import plan_service

STATE_PATH = os.path.join(plan_database.DATA_DIR, "plan_daily_schedule_state.json")
STATE_LOCK_PATH = STATE_PATH + ".lock"
SCHEDULER_LOCK_PATH = os.path.join(plan_database.DATA_DIR, "plan_daily_schedule_scheduler.lock")
_scheduler_started = False
_scheduler_lock = threading.Lock()
_RETRY_INTERVAL_SEC = 300


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


def edit_text(token: str, chat_id: str, message_id: int, text: str) -> bool:
    if not token or not chat_id or not message_id:
        return False
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": (text or "")[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    try:
        _request(
            f"https://api.telegram.org/bot{token}/editMessageText",
            payload,
            {"Content-Type": "application/json; charset=utf-8"},
            timeout=20,
        )
        return True
    except plan_service.PlanError as exc:
        if "message is not modified" in str(exc.message or "").lower():
            return True
        return False


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


def _chat_id(value) -> str:
    return str(value or "").strip()


def _message_ids(raw) -> list[int]:
    if not isinstance(raw, list):
        return []
    ids: list[int] = []
    for item in raw:
        text = str(item).strip()
        if text.lstrip("-").isdigit():
            value = int(text)
            if value not in ids:
                ids.append(value)
    return ids


def _load_state() -> dict:
    empty = {"messages": {}, "lastSent": None, "lastError": None, "lastAt": None, "lastRetryAt": None}
    if not os.path.isfile(STATE_PATH):
        return empty
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return empty
        data.setdefault("messages", {})
        data.setdefault("lastRetryAt", None)
        return data
    except (OSError, json.JSONDecodeError):
        return empty


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, STATE_PATH)


def _should_retry(state: dict, now: datetime) -> bool:
    last_retry = state.get("lastRetryAt")
    if not last_retry:
        return True
    try:
        previous = datetime.fromisoformat(str(last_retry))
    except ValueError:
        return True
    return (now - previous).total_seconds() >= _RETRY_INTERVAL_SEC


def _deliver_to_chat(token: str, chat_id: str, html: str, previous_ids: list[int]) -> list[int]:
    keep_id: int | None = None
    for old_id in reversed(previous_ids):
        if edit_text(token, chat_id, old_id, html):
            keep_id = old_id
            break
    if keep_id is None:
        keep_id = send_text(token, chat_id, html)
    kept: list[int] = []
    for old_id in previous_ids:
        if keep_id and old_id == keep_id:
            continue
        if not delete_message(token, chat_id, old_id):
            kept.append(old_id)
    if keep_id:
        kept.append(keep_id)
    return kept


def send_daily_list(test: bool = False) -> dict:
    with job_lock.exclusive_lock(STATE_LOCK_PATH):
        return _send_daily_list(test=test)


def _send_daily_list(test: bool = False) -> dict:
    settings = plan_service.get_settings()
    if not test and not settings.get("dailyScheduleEnabled"):
        raise plan_service.PlanError("Ежедневная отправка списка дел выключена")
    token = (settings.get("telegramBotToken") or "").strip()
    recipients = []
    for item in settings.get("chatIds") or []:
        value = _chat_id(item)
        if value and value not in recipients:
            recipients.append(value)
    if not token:
        raise plan_service.PlanError("Укажите токен бота")
    if not recipients:
        raise plan_service.PlanError("Укажите chat id")

    html = plan_service.format_today_html()
    today = datetime.now().date().isoformat()
    state = _load_state()
    if not test and state.get("lastSent") == today:
        return {"ok": True, "test": test, "recipients": len(recipients), "sentNow": 0}

    # Бронь дня до запросов в Telegram.
    if not test:
        state["lastSent"] = today
        state["lastAt"] = datetime.now().isoformat(timespec="seconds")
        _save_state(state)

    messages = {
        _chat_id(key): _message_ids(value)
        for key, value in dict(state.get("messages") or {}).items()
        if _chat_id(key)
    }
    errors: list[str] = []
    sent_now = 0
    for chat_id in recipients:
        try:
            kept = _deliver_to_chat(token, chat_id, html, messages.get(chat_id, []))
        except plan_service.PlanError as exc:
            errors.append(f"{chat_id}: {exc.message}")
            continue
        messages[chat_id] = kept
        sent_now += 1
        state["messages"] = messages
        state["lastAt"] = datetime.now().isoformat(timespec="seconds")
        _save_state(state)

    now = datetime.now().isoformat(timespec="seconds")
    state["messages"] = messages
    state["lastAt"] = now
    if errors:
        state["lastError"] = "; ".join(errors)
        if not test:
            # Снимаем бронь только если никому не ушло — иначе день остаётся закрытым.
            if sent_now == 0:
                state["lastSent"] = None
            state["lastRetryAt"] = now
        _save_state(state)
        if sent_now == 0:
            raise plan_service.PlanError("Не удалось отправить: " + "; ".join(errors))
        raise plan_service.PlanError("Отправлено частично. Ошибки: " + "; ".join(errors))

    state["lastError"] = None
    if not test:
        state["lastSent"] = today
        state["lastRetryAt"] = None
    _save_state(state)
    return {"ok": True, "test": test, "recipients": len(recipients), "sentNow": sent_now}


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
    today = now.date().isoformat()
    with job_lock.exclusive_lock(STATE_LOCK_PATH):
        state = _load_state()
        if state.get("lastSent") == today:
            return
        if not _should_retry(state, now):
            return
        try:
            _send_daily_list(test=False)
        except Exception as exc:
            state = _load_state()
            state["lastError"] = str(getattr(exc, "message", None) or exc)
            state["lastAt"] = datetime.now().isoformat(timespec="seconds")
            state["lastRetryAt"] = datetime.now().isoformat(timespec="seconds")
            _save_state(state)


def start_scheduler() -> None:
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    def loop() -> None:
        leader = job_lock.try_open_lock(SCHEDULER_LOCK_PATH)
        if leader is None:
            return
        try:
            while True:
                try:
                    _tick()
                except Exception:
                    pass
                time.sleep(30)
        finally:
            leader.release()

    thread = threading.Thread(target=loop, name="plan-daily-schedule", daemon=True)
    thread.start()
