"""Отправка Telegram-сообщений и ежедневное расписание с веб-сервера."""

from __future__ import annotations

import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

import database
import service

STATE_PATH = os.path.join(database.DATA_DIR, "daily_schedule_state.json")
_scheduler_started = False
_scheduler_lock = threading.Lock()
_send_lock = threading.Lock()


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
        raise service.AppError(description)
    parsed = json.loads(raw)
    if not parsed.get("ok"):
        raise service.AppError(parsed.get("description") or "Telegram отклонил запрос")
    return parsed


def send_text(token: str, chat_id: str, text: str) -> int | None:
    if not token or not chat_id:
        raise service.AppError("Укажите токен бота и chat id")
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


def send_document(token: str, chat_id: str, filename: str, content: bytes, caption: str = "") -> int | None:
    if not token or not chat_id:
        raise service.AppError("Укажите токен бота и chat id")
    boundary = "----ClassHubBoundary"
    body = io.BytesIO()

    def field(name: str, value: str) -> None:
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.write(value.encode("utf-8"))
        body.write(b"\r\n")

    field("chat_id", chat_id)
    if caption:
        field("caption", caption[:1024])
    body.write(f"--{boundary}\r\n".encode())
    body.write(
        f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'.encode()
    )
    body.write(b"Content-Type: application/octet-stream\r\n\r\n")
    body.write(content)
    body.write(f"\r\n--{boundary}--\r\n".encode())
    parsed = _request(
        f"https://api.telegram.org/bot{token}/sendDocument",
        body.getvalue(),
        {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        timeout=90,
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
    except service.AppError:
        return False


def _empty_state() -> dict:
    return {"messages": {}, "sentByChat": {}, "lastSent": None, "lastError": None, "lastAt": None}


def _load_state() -> dict:
    if not os.path.isfile(STATE_PATH):
        return _empty_state()
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return _empty_state()
        data.setdefault("messages", {})
        data.setdefault("sentByChat", {})
        return data
    except (OSError, json.JSONDecodeError):
        return _empty_state()


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)


def _chat_id(value) -> str:
    return str(value or "").strip()


def _extra_ids(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = raw.replace(",", "\n").replace(";", "\n").split("\n")
    elif isinstance(raw, (list, tuple, set)):
        parts = raw
    else:
        parts = [raw]
    ids: list[str] = []
    for item in parts:
        value = _chat_id(item)
        if value and value not in ids:
            ids.append(value)
    return ids


def _recipients(settings: dict) -> list[str]:
    ids: list[str] = []
    main = _chat_id(settings.get("telegramChatId"))
    if main:
        ids.append(main)
    extras = settings.get("extraChatIds")
    if extras is None:
        extras = settings.get("dailyScheduleExtraChatIds")
    for value in _extra_ids(extras):
        if value not in ids:
            ids.append(value)
    return ids


def _already_sent(sent_by_chat: dict, chat_id: str, today: str) -> bool:
    return str(sent_by_chat.get(chat_id) or "") == today


def send_daily_schedule(test: bool = False) -> dict:
    with _send_lock:
        return _send_daily_schedule(test=test)


def _send_daily_schedule(test: bool = False) -> dict:
    settings = service.get_settings()
    if not test and not settings.get("dailyScheduleEnabled", True):
        raise service.AppError("Ежедневная отправка расписания выключена")
    token = _chat_id(settings.get("telegramBotToken"))
    recipients = _recipients(settings)
    if not token:
        raise service.AppError("Укажите токен бота")
    if not recipients:
        raise service.AppError("Укажите chat id")
    html = service.format_today_schedule_html()
    today = service.today().isoformat()
    state = _load_state()
    messages = dict(state.get("messages") or {})
    sent_by_chat = dict(state.get("sentByChat") or {})
    errors: list[str] = []
    sent_now = 0
    for chat_id in recipients:
        if not test and _already_sent(sent_by_chat, chat_id, today):
            continue
        try:
            new_id = send_text(token, chat_id, html)
        except service.AppError as exc:
            errors.append(f"{chat_id}: {exc.message}")
            continue
        old_ids = [int(item) for item in messages.get(chat_id, []) if str(item).isdigit() or isinstance(item, int)]
        kept: list[int] = []
        for old_id in old_ids:
            if new_id and old_id == new_id:
                continue
            if not delete_message(token, chat_id, old_id):
                kept.append(old_id)
        if new_id:
            kept.append(new_id)
        messages[chat_id] = kept
        sent_now += 1
        if not test:
            sent_by_chat[chat_id] = today
            state["messages"] = messages
            state["sentByChat"] = sent_by_chat
            state["lastAt"] = datetime.now().isoformat(timespec="seconds")
            _save_state(state)
    now = datetime.now().isoformat(timespec="seconds")
    state["messages"] = messages
    state["sentByChat"] = sent_by_chat
    state["lastAt"] = now
    pending = [chat_id for chat_id in recipients if test or not _already_sent(sent_by_chat, chat_id, today)]
    if errors:
        state["lastError"] = "; ".join(errors)
        if not test and not pending:
            state["lastSent"] = today
        _save_state(state)
        if sent_now == 0 and pending:
            raise service.AppError("Не удалось отправить: " + "; ".join(errors))
        raise service.AppError("Отправлено частично. Ошибки: " + "; ".join(errors))
    state["lastError"] = None
    if not test:
        state["lastSent"] = today
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
        settings = service.get_settings()
    except Exception:
        return
    if not settings.get("dailyScheduleEnabled", True):
        return
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute
    target = int(settings.get("dailyScheduleMinutes") or 7 * 60)
    if current_minutes < target:
        return
    today = service.today().isoformat()
    state = _load_state()
    recipients = _recipients(settings)
    sent_by_chat = state.get("sentByChat") or {}
    if state.get("lastSent") == today:
        return
    if recipients and all(_already_sent(sent_by_chat, chat_id, today) for chat_id in recipients):
        state["lastSent"] = today
        state["lastError"] = None
        _save_state(state)
        return
    try:
        send_daily_schedule(test=False)
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

    thread = threading.Thread(target=loop, name="daily-schedule", daemon=True)
    thread.start()


# Имена из app.py
send_daily_schedule = send_daily_schedule
send_document = send_document
start_scheduler = start_scheduler
send_text = send_text
