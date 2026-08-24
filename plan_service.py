"""CRUD дел совместного планирования. Изолирован от ClassHub."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import plan_database

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
IMPORTANCE_VALUES = ("low", "medium", "high")


class PlanError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row_to_event(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"] or "",
        "date": row["event_date"],
        "time": row["event_time"],
        "durationMinutes": row["duration_minutes"],
        "importance": row["importance"],
        "author": row["author"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "source": "plan",
        "readonly": False,
    }


def _normalize(data: dict, *, partial: bool = False, existing: dict | None = None) -> dict:
    source = dict(existing or {})
    if data:
        source.update({k: v for k, v in data.items() if v is not None})

    title = str(source.get("title") or "").strip()
    description = str(source.get("description") or "").strip()
    date_value = str(source.get("date") or source.get("event_date") or "").strip()
    time_value = str(source.get("time") or source.get("event_time") or "").strip()
    author = str(source.get("author") or "").strip()
    importance = str(source.get("importance") or "medium").strip().lower()
    duration = source.get("durationMinutes", source.get("duration_minutes", 60))

    if not partial or "title" in data:
        if not title:
            raise PlanError("Укажите название дела")
        if len(title) > 200:
            raise PlanError("Название слишком длинное")
    if len(description) > 4000:
        raise PlanError("Описание слишком длинное")
    if not DATE_RE.match(date_value):
        raise PlanError("Дата должна быть в формате ГГГГ-ММ-ДД")
    try:
        datetime.strptime(date_value, "%Y-%m-%d")
    except ValueError as exc:
        raise PlanError("Некорректная дата") from exc
    if not TIME_RE.match(time_value):
        raise PlanError("Время должно быть в формате ЧЧ:ММ")
    try:
        datetime.strptime(time_value, "%H:%M")
    except ValueError as exc:
        raise PlanError("Некорректное время") from exc
    if importance not in IMPORTANCE_VALUES:
        raise PlanError("Важность: low, medium или high")
    if not author:
        raise PlanError("Укажите имя")
    if len(author) > 80:
        raise PlanError("Имя слишком длинное")
    try:
        duration_int = int(duration)
    except (TypeError, ValueError) as exc:
        raise PlanError("Длительность должна быть числом") from exc
    if duration_int < 15 or duration_int > 24 * 60:
        raise PlanError("Длительность — от 15 минут до 24 часов")

    return {
        "title": title,
        "description": description,
        "event_date": date_value,
        "event_time": time_value,
        "duration_minutes": duration_int,
        "importance": importance,
        "author": author,
    }


def list_events(date_from: str | None, date_to: str | None) -> list[dict]:
    date_from = (date_from or "").strip()
    date_to = (date_to or "").strip()
    if date_from and not DATE_RE.match(date_from):
        raise PlanError("Параметр from должен быть датой ГГГГ-ММ-ДД")
    if date_to and not DATE_RE.match(date_to):
        raise PlanError("Параметр to должен быть датой ГГГГ-ММ-ДД")

    sql = "SELECT * FROM events"
    params: list[str] = []
    clauses: list[str] = []
    if date_from:
        clauses.append("event_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("event_date <= ?")
        params.append(date_to)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY event_date, event_time, id"

    with plan_database.db_cursor() as conn:
        rows = conn.execute(sql, params).fetchall()
    own = [_row_to_event(row) for row in rows]
    merged = own + _classhub_events(date_from, date_to)
    merged.sort(key=lambda item: (item["date"], item["time"], item["source"] != "classhub", item["id"]))
    return merged


def get_event(event_id: int) -> dict:
    if event_id < 0:
        event = _classhub_event_by_occurrence(-event_id)
        if event is None:
            raise PlanError("Дело не найдено", 404)
        return event
    with plan_database.db_cursor() as conn:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        raise PlanError("Дело не найдено", 404)
    return _row_to_event(row)


def create_event(data: dict) -> dict:
    payload = _normalize(data or {})
    now = _now()
    with plan_database.db_cursor(transaction=True) as conn:
        cur = conn.execute(
            """
            INSERT INTO events (
                title, description, event_date, event_time, duration_minutes,
                importance, author, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["title"],
                payload["description"],
                payload["event_date"],
                payload["event_time"],
                payload["duration_minutes"],
                payload["importance"],
                payload["author"],
                now,
                now,
            ),
        )
        event_id = int(cur.lastrowid)
    return get_event(event_id)


def update_event(event_id: int, data: dict) -> dict:
    _ensure_writable(event_id)
    existing = get_event(event_id)
    merged = {
        "title": existing["title"],
        "description": existing["description"],
        "date": existing["date"],
        "time": existing["time"],
        "durationMinutes": existing["durationMinutes"],
        "importance": existing["importance"],
        "author": existing["author"],
    }
    incoming = data or {}
    # Автор создателя не меняется при правке
    incoming.pop("author", None)
    merged.update(incoming)
    payload = _normalize(merged)
    now = _now()
    with plan_database.db_cursor(transaction=True) as conn:
        conn.execute(
            """
            UPDATE events SET
                title = ?, description = ?, event_date = ?, event_time = ?,
                duration_minutes = ?, importance = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload["title"],
                payload["description"],
                payload["event_date"],
                payload["event_time"],
                payload["duration_minutes"],
                payload["importance"],
                now,
                event_id,
            ),
        )
    return get_event(event_id)


def delete_event(event_id: int) -> None:
    _ensure_writable(event_id)
    get_event(event_id)
    with plan_database.db_cursor(transaction=True) as conn:
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))


def _ensure_writable(event_id: int) -> None:
    if event_id < 0:
        raise PlanError("Занятия ClassHub нельзя изменять из планирования", 403)


def _minutes_to_time(minutes: int) -> str:
    total = max(0, int(minutes or 0))
    hours, mins = divmod(total, 60)
    return f"{hours:02d}:{mins:02d}"


def _lesson_to_plan_event(lesson: dict) -> dict:
    occ = lesson["occurrence"]
    student = lesson.get("student") or {}
    status = occ.get("status") or "EXPECTED"
    status_label = {
        "EXPECTED": "Ожидается",
        "CONDUCTED": "Проведено",
        "CANCELLED": "Отменено",
    }.get(status, status)
    location = occ.get("locationType") or ""
    if location == "ONLINE":
        place = "Онлайн"
    else:
        place = str(occ.get("address") or "").strip() or "Офлайн"
    notes = str(occ.get("notes") or "").strip()
    grade = str(student.get("grade") or "").strip()
    duration = int(occ.get("durationMinutes") or 60)
    lines = [f"Ученик: {student.get('name') or '—'}"]
    if grade:
        lines.append(f"Класс: {grade}")
    lines.append(f"Предмет: {lesson.get('subjectName') or 'Предмет'}")
    lines.append(f"Формат: {place}")
    lines.append(f"Длительность: {duration} мин")
    lines.append(f"Статус: {status_label}")
    if notes:
        lines.append(f"Заметки: {notes}")
    import service
    day = service.from_epoch_day(occ["dateEpochDay"])
    return {
        "id": -int(occ["id"]),
        "title": "РЕПИК",
        "description": "\n".join(lines),
        "date": day.isoformat(),
        "time": _minutes_to_time(occ.get("startTimeMinutes") or 0),
        "durationMinutes": max(15, duration),
        "importance": "high",
        "author": student.get("name") or "ClassHub",
        "createdAt": "",
        "updatedAt": "",
        "source": "classhub",
        "readonly": True,
    }


def _classhub_events(date_from: str, date_to: str) -> list[dict]:
    if not date_from and not date_to:
        return []
    try:
        import service
    except Exception:
        return []
    start = date_from or date_to
    end = date_to or date_from
    try:
        from_day = service.to_epoch_day(datetime.strptime(start, "%Y-%m-%d").date())
        to_day = service.to_epoch_day(datetime.strptime(end, "%Y-%m-%d").date())
        lessons = service.lessons_in_range(from_day, to_day, include_archived=True)
    except Exception:
        return []
    return [_lesson_to_plan_event(lesson) for lesson in lessons]


def _classhub_event_by_occurrence(occurrence_id: int) -> dict | None:
    try:
        import service
        lesson = service.get_lesson(occurrence_id)
    except Exception:
        return None
    return _lesson_to_plan_event(lesson)


DEFAULT_SETTINGS = {
    "reminderMinutes": 30,
    "notificationsEnabled": True,
    "telegramBotToken": "",
    "chatIds": [],
    "dailyScheduleEnabled": False,
    "dailyScheduleMinutes": 7 * 60,
}

MONTHS_SHORT = [
    "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]


def _parse_chat_ids(raw: str) -> list[str]:
    ids: list[str] = []
    for item in (raw or "").replace(",", "\n").replace(";", "\n").splitlines():
        value = item.strip()
        if value and value not in ids:
            ids.append(value)
    return ids


def _row_to_settings(row) -> dict:
    return {
        "reminderMinutes": int(row["reminder_minutes"] or 30),
        "notificationsEnabled": bool(row["notifications_enabled"]),
        "telegramBotToken": row["telegram_bot_token"] or "",
        "chatIds": _parse_chat_ids(row["telegram_chat_ids"] or ""),
        "dailyScheduleEnabled": bool(row["daily_enabled"]),
        "dailyScheduleMinutes": int(row["daily_minutes"] or 7 * 60),
    }


def get_settings() -> dict:
    plan_database.init_db()
    with plan_database.db_cursor() as conn:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    if row is None:
        return dict(DEFAULT_SETTINGS)
    return _row_to_settings(row)


def update_settings(data: dict) -> dict:
    current = get_settings()
    payload = dict(data or {})
    reminder = payload.get("reminderMinutes", current["reminderMinutes"])
    try:
        reminder_int = int(reminder)
    except (TypeError, ValueError) as exc:
        raise PlanError("Напоминание — число минут") from exc
    if reminder_int < 1 or reminder_int > 24 * 60:
        raise PlanError("Напоминание — от 1 минуты до 24 часов")
    enabled = payload.get("notificationsEnabled", current["notificationsEnabled"])
    token = str(payload.get("telegramBotToken", current["telegramBotToken"]) or "").strip()
    if "chatIds" in payload:
        raw_ids = payload.get("chatIds") or []
        if isinstance(raw_ids, str):
            chat_ids = _parse_chat_ids(raw_ids)
        else:
            chat_ids = []
            for item in raw_ids:
                value = str(item).strip()
                if value and value not in chat_ids:
                    chat_ids.append(value)
    else:
        chat_ids = list(current["chatIds"])
    daily_enabled = payload.get("dailyScheduleEnabled", current["dailyScheduleEnabled"])
    minutes = payload.get("dailyScheduleMinutes", current["dailyScheduleMinutes"])
    try:
        minutes_int = int(minutes)
    except (TypeError, ValueError) as exc:
        raise PlanError("Время отправки задаётся в минутах от полуночи") from exc
    if minutes_int < 0 or minutes_int > 23 * 60 + 59:
        raise PlanError("Некорректное время отправки")
    with plan_database.db_cursor(transaction=True) as conn:
        conn.execute(
            """
            INSERT INTO settings (
                id, reminder_minutes, notifications_enabled, telegram_bot_token,
                telegram_chat_ids, daily_enabled, daily_minutes
            ) VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                reminder_minutes = excluded.reminder_minutes,
                notifications_enabled = excluded.notifications_enabled,
                telegram_bot_token = excluded.telegram_bot_token,
                telegram_chat_ids = excluded.telegram_chat_ids,
                daily_enabled = excluded.daily_enabled,
                daily_minutes = excluded.daily_minutes
            """,
            (
                reminder_int,
                1 if enabled else 0,
                token,
                "\n".join(chat_ids),
                1 if daily_enabled else 0,
                minutes_int,
            ),
        )
    return get_settings()


def is_cancelled_event(event: dict) -> bool:
    if event.get("source") != "classhub":
        return False
    return "Статус: Отменено" in (event.get("description") or "")


def format_today_html() -> str:
    from datetime import date as date_cls

    day = date_cls.today()
    iso = day.isoformat()
    events = [
        event
        for event in list_events(iso, iso)
        if not is_cancelled_event(event)
    ]
    title = f"📅 Дела на {day.day} {MONTHS_SHORT[day.month - 1]} {day.year}"

    def esc(text: str) -> str:
        return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    if not events:
        return f"<b>{esc(title)}</b>\n\nНа сегодня дел нет."
    blocks = []
    for event in events:
        blocks.append(
            f"<b>{esc(event['time'])}</b> · {esc(event['title'])}\n"
            f"👤 {esc(event.get('author') or '—')}"
        )
    body = "\n————————————\n".join(blocks)
    return f"<b>{esc(title)}</b>\n\n{body}\n\nДел: {len(events)}"
