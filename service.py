"""Бизнес-логика веб-приложения, совместимая с мобильным TutorRepository."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any

from database import db_cursor

STATUS_EXPECTED = "EXPECTED"
STATUS_CONDUCTED = "CONDUCTED"
STATUS_CANCELLED = "CANCELLED"
LOCATION_ONLINE = "ONLINE"
LOCATION_OFFLINE = "OFFLINE"

MONTHS_SHORT = [
    "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]
MONTHS_FULL = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


class AppError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class ConflictError(AppError):
    def __init__(self, message: str = "Конфликт расписания: занятие пересекается с другим"):
        super().__init__(message, 409)


def today() -> date:
    return date.today()


def to_epoch_day(value: date) -> int:
    return (value - date(1970, 1, 1)).days


def from_epoch_day(epoch_day: int) -> date:
    return date(1970, 1, 1) + timedelta(days=int(epoch_day))


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def weekday_number(value: date) -> int:
    return value.isoweekday()


def month_bounds(anchor: date) -> tuple[int, int]:
    first = date(anchor.year, anchor.month, 1)
    nxt = date(anchor.year + 1, 1, 1) if anchor.month == 12 else date(anchor.year, anchor.month + 1, 1)
    return to_epoch_day(first), to_epoch_day(nxt - timedelta(days=1))


def week_bounds(anchor: date) -> tuple[int, int]:
    monday = anchor - timedelta(days=anchor.isoweekday() - 1)
    return to_epoch_day(monday), to_epoch_day(monday + timedelta(days=6))


def now_ms() -> int:
    return int(time.time() * 1000)


def start_ms(epoch_day: int, start_minutes: int) -> int:
    dt = datetime.combine(from_epoch_day(epoch_day), datetime.min.time())
    return int(dt.timestamp() * 1000) + start_minutes * 60_000


def end_ms(epoch_day: int, start_minutes: int, duration: int) -> int:
    return start_ms(epoch_day, start_minutes) + duration * 60_000


def lesson_is_ongoing(epoch_day: int, start_minutes: int, duration: int, now: int | None = None) -> bool:
    now = now or now_ms()
    return start_ms(epoch_day, start_minutes) <= now < end_ms(epoch_day, start_minutes, duration)


def as_dict(row) -> dict[str, Any] | None:
    return None if row is None else dict(row)


def load_subjects(conn, student_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM student_subjects WHERE studentId = ? ORDER BY name ASC",
            (student_id,),
        )
    ]


def with_subjects(students: list[dict], subjects: list[dict]) -> list[dict]:
    grouped: dict[int, list[dict]] = {}
    for sub in subjects:
        grouped.setdefault(sub["studentId"], []).append(sub)
    result = []
    for student in students:
        attached = grouped.get(student["id"], [])
        item = dict(student)
        item["isArchived"] = bool(student["isArchived"])
        item["subjects"] = attached
        if not attached:
            item["subjectsLabel"] = "—"
        elif len(attached) == 1:
            item["subjectsLabel"] = attached[0]["name"]
        else:
            item["subjectsLabel"] = ", ".join(s["name"] for s in attached)
        result.append(item)
    return result


def list_students(archived: bool = False) -> list[dict]:
    with db_cursor() as conn:
        students = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM students WHERE isArchived = ? ORDER BY name ASC",
                (1 if archived else 0,),
            )
        ]
        subjects = [dict(r) for r in conn.execute("SELECT * FROM student_subjects")]
        return with_subjects(students, subjects)


def get_student(student_id: int) -> dict:
    with db_cursor() as conn:
        student = as_dict(conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone())
        if student is None:
            raise AppError("Ученик не найден", 404)
        return with_subjects([student], load_subjects(conn, student_id))[0]


def add_student(name: str, grade: str, subjects: list[dict], address: str | None = None) -> int:
    name = (name or "").strip()
    grade = (grade or "").strip()
    if not name:
        raise AppError("Укажите имя ученика")
    if not subjects:
        raise AppError("Добавьте хотя бы один предмет")
    cleaned = []
    seen: list[str] = []
    for item in subjects:
        sub_name = (item.get("name") or "").strip()
        price = float(item.get("price") or 0)
        if not sub_name:
            raise AppError("Укажите название предмета")
        if price <= 0:
            raise AppError("Стоимость должна быть больше нуля")
        key = sub_name.lower()
        if key in seen:
            raise AppError("Предметы не должны повторяться")
        seen.append(key)
        cleaned.append((sub_name, price))
    with db_cursor(transaction=True) as conn:
        cur = conn.execute(
            "INSERT INTO students (name, grade, address, isArchived, createdAt) VALUES (?, ?, ?, 0, ?)",
            (name, grade, (address or "").strip() or None, now_ms()),
        )
        student_id = int(cur.lastrowid)
        for sub_name, price in cleaned:
            conn.execute(
                "INSERT INTO student_subjects (studentId, name, price) VALUES (?, ?, ?)",
                (student_id, sub_name, price),
            )
        return student_id


def update_student(student_id: int, name: str, grade: str, address: str | None) -> None:
    name = (name or "").strip()
    if not name:
        raise AppError("Укажите имя ученика")
    with db_cursor(transaction=True) as conn:
        if conn.execute("SELECT id FROM students WHERE id = ?", (student_id,)).fetchone() is None:
            raise AppError("Ученик не найден", 404)
        conn.execute(
            "UPDATE students SET name = ?, grade = ?, address = ? WHERE id = ?",
            (name, (grade or "").strip(), (address or "").strip() or None, student_id),
        )


def set_student_archived(student_id: int, archived: bool) -> None:
    with db_cursor(transaction=True) as conn:
        conn.execute(
            "UPDATE students SET isArchived = ? WHERE id = ?",
            (1 if archived else 0, student_id),
        )


def delete_student(student_id: int) -> None:
    with db_cursor(transaction=True) as conn:
        conn.execute("DELETE FROM students WHERE id = ?", (student_id,))


def _unique_subject(conn, student_id: int, name: str, exclude_id: int | None = None) -> None:
    for row in conn.execute("SELECT id, name FROM student_subjects WHERE studentId = ?", (student_id,)):
        if exclude_id is not None and row["id"] == exclude_id:
            continue
        if row["name"].strip().lower() == name.strip().lower():
            raise AppError(f"У ученика уже есть предмет «{name.strip()}»")


def add_subject(student_id: int, name: str, price: float) -> int:
    name = (name or "").strip()
    if not name:
        raise AppError("Укажите название предмета")
    if price <= 0:
        raise AppError("Стоимость должна быть больше нуля")
    with db_cursor(transaction=True) as conn:
        if conn.execute("SELECT id FROM students WHERE id = ?", (student_id,)).fetchone() is None:
            raise AppError("Ученик не найден", 404)
        _unique_subject(conn, student_id, name)
        cur = conn.execute(
            "INSERT INTO student_subjects (studentId, name, price) VALUES (?, ?, ?)",
            (student_id, name, price),
        )
        return int(cur.lastrowid)


def update_subject(subject_id: int, name: str, price: float) -> None:
    name = (name or "").strip()
    if not name:
        raise AppError("Укажите название предмета")
    if price <= 0:
        raise AppError("Стоимость должна быть больше нуля")
    with db_cursor(transaction=True) as conn:
        old = as_dict(conn.execute("SELECT * FROM student_subjects WHERE id = ?", (subject_id,)).fetchone())
        if old is None:
            raise AppError("Предмет не найден", 404)
        _unique_subject(conn, old["studentId"], name, exclude_id=subject_id)
        conn.execute(
            "UPDATE student_subjects SET name = ?, price = ? WHERE id = ?",
            (name, price, subject_id),
        )
        if abs(old["price"] - price) > 0.001:
            conn.execute(
                "UPDATE lesson_occurrences SET price = ? WHERE studentSubjectId = ? AND status = 'EXPECTED'",
                (price, subject_id),
            )
            _rebalance_payments(conn, old["studentId"])


def delete_subject(subject_id: int) -> None:
    with db_cursor(transaction=True) as conn:
        subject = as_dict(conn.execute("SELECT * FROM student_subjects WHERE id = ?", (subject_id,)).fetchone())
        if subject is None:
            return
        used = conn.execute(
            "SELECT COUNT(*) FROM lesson_occurrences WHERE studentSubjectId = ?", (subject_id,)
        ).fetchone()[0]
        used += conn.execute(
            "SELECT COUNT(*) FROM lesson_series WHERE studentSubjectId = ?", (subject_id,)
        ).fetchone()[0]
        if used > 0:
            raise AppError("Нельзя удалить предмет: есть связанные занятия")
        remaining = conn.execute(
            "SELECT COUNT(*) FROM student_subjects WHERE studentId = ?", (subject["studentId"],)
        ).fetchone()[0]
        if remaining <= 1:
            raise AppError("У ученика должен остаться хотя бы один предмет")
        conn.execute("DELETE FROM student_subjects WHERE id = ?", (subject_id,))


def _lesson_payload(occ: dict, student: dict, subject: dict | None) -> dict:
    price = occ["price"]
    paid = occ["paidAmount"]
    fully = occ["status"] == STATUS_CONDUCTED and paid >= price - 0.001
    return {
        "occurrence": occ,
        "occurrence": occ,
        "student": {**student, "isArchived": bool(student["isArchived"])},
        "subject": subject,
        "subjectName": subject["name"] if subject and str(subject["name"]).strip() else "Предмет",
        "lessonPrice": price,
        "isFullyPaid": fully,
        "isFullyPaid": fully,
        "isPartiallyPaid": paid > 0 and not fully,
    }


def join_lessons(conn, occurrences, include_archived: bool = False) -> list[dict]:
    student_sql = "SELECT * FROM students" if include_archived else "SELECT * FROM students WHERE isArchived = 0"
    students = {r["id"]: dict(r) for r in conn.execute(student_sql)}
    subjects = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM student_subjects")}
    result = []
    for occ in occurrences:
        occ_d = dict(occ)
        student = students.get(occ_d["studentId"])
        if student is None:
            continue
        student = {**student, "isArchived": bool(student["isArchived"])}
        result.append(_lesson_payload(occ_d, student, subjects.get(occ_d["studentSubjectId"])))
    return result


def lessons_in_range(
    from_day: int,
    to_day: int,
    upcoming_only: bool = False,
    include_archived: bool = False,
) -> list[dict]:
    extra = "AND status = 'EXPECTED'" if upcoming_only else ""
    sql = f"""
        SELECT * FROM lesson_occurrences
        WHERE dateEpochDay >= ? AND dateEpochDay <= ? {extra}
        ORDER BY dateEpochDay ASC, startTimeMinutes ASC
    """
    with db_cursor() as conn:
        return join_lessons(conn, conn.execute(sql, (from_day, to_day)), include_archived=include_archived)


def get_lesson(occurrence_id: int) -> dict:
    with db_cursor() as conn:
        occ = as_dict(conn.execute("SELECT * FROM lesson_occurrences WHERE id = ?", (occurrence_id,)).fetchone())
        if occ is None:
            raise AppError("Занятие не найдено", 404)
        student = as_dict(conn.execute("SELECT * FROM students WHERE id = ?", (occ["studentId"],)).fetchone())
        if student is None:
            raise AppError("Ученик не найден", 404)
        subject = as_dict(
            conn.execute("SELECT * FROM student_subjects WHERE id = ?", (occ["studentSubjectId"],)).fetchone()
        )
        series = as_dict(conn.execute("SELECT * FROM lesson_series WHERE id = ?", (occ["seriesId"],)).fetchone())
        payload = _lesson_payload(occ, student, subject)
        payload["series"] = series
        payload["subjects"] = load_subjects(conn, occ["studentId"])
        return payload


def get_series(series_id: int) -> dict:
    with db_cursor() as conn:
        series = as_dict(conn.execute("SELECT * FROM lesson_series WHERE id = ?", (series_id,)).fetchone())
        if series is None:
            raise AppError("Серия не найдена", 404)
        series["isWeekly"] = bool(series["isWeekly"])
        return series


def compute_monthly_stats(occurrences: list[dict]) -> dict:
    active = [o for o in occurrences if o["status"] != STATUS_CANCELLED]
    conducted = [o for o in active if o["status"] == STATUS_CONDUCTED]
    expected = sum(o["price"] for o in active)
    earned = sum(o["price"] for o in conducted)
    paid = sum(o["paidAmount"] for o in conducted)
    return {
        "plannedCount": len(active),
        "conductedCount": len(conducted),
        "cancelledCount": sum(1 for o in occurrences if o["status"] == STATUS_CANCELLED),
        "expectedEarnings": expected,
        "earned": earned,
        "paidAmount": paid,
        "unpaidAmount": max(earned - paid, 0.0),
        "paidLessonsCount": sum(1 for o in conducted if o["paidAmount"] >= o["price"] - 0.001),
    }


def dashboard(month_iso: str | None = None) -> dict:
    anchor = parse_iso_date(month_iso) if month_iso else today()
    month_from, month_to = month_bounds(anchor)
    week_from, week_to = week_bounds(today())
    now = now_ms()
    today_day = to_epoch_day(today())
    with db_cursor() as conn:
        student_count = conn.execute("SELECT COUNT(*) FROM students WHERE isArchived = 0").fetchone()[0]
        month_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT lo.* FROM lesson_occurrences lo
                JOIN students s ON s.id = lo.studentId
                WHERE lo.dateEpochDay BETWEEN ? AND ? AND s.isArchived = 0
                """,
                (month_from, month_to),
            )
        ]
        week_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT lo.* FROM lesson_occurrences lo
                JOIN students s ON s.id = lo.studentId
                WHERE lo.dateEpochDay BETWEEN ? AND ? AND s.isArchived = 0
                """,
                (week_from, week_to),
            )
        ]
        recent = join_lessons(
            conn,
            conn.execute(
                """
                SELECT * FROM lesson_occurrences
                WHERE dateEpochDay BETWEEN ? AND ?
                ORDER BY dateEpochDay, startTimeMinutes
                """,
                (today_day - 7, today_day),
            ),
        )
        upcoming = join_lessons(
            conn,
            conn.execute(
                """
                SELECT * FROM lesson_occurrences
                WHERE dateEpochDay BETWEEN ? AND ? AND status = 'EXPECTED'
                ORDER BY dateEpochDay, startTimeMinutes
                """,
                (today_day, today_day + 1),
            ),
        )
    week_active = [o for o in week_rows if o["status"] != STATUS_CANCELLED]
    ongoing = [
        lesson
        for lesson in recent
        if lesson["occurrence"]["dateEpochDay"] == today_day
        and lesson["occurrence"]["status"] != STATUS_CANCELLED
        and lesson_is_ongoing(
            lesson["occurrence"]["dateEpochDay"],
            lesson["occurrence"]["startTimeMinutes"],
            lesson["occurrence"]["durationMinutes"],
            now,
        )
    ]
    needs_status = [
        lesson
        for lesson in recent
        if lesson["occurrence"]["status"] == STATUS_EXPECTED
        and end_ms(
            lesson["occurrence"]["dateEpochDay"],
            lesson["occurrence"]["startTimeMinutes"],
            lesson["occurrence"]["durationMinutes"],
        )
        <= now
    ]
    hidden = {lesson["occurrence"]["id"] for lesson in ongoing + needs_status}
    upcoming_filtered = [
        lesson
        for lesson in upcoming
        if lesson["occurrence"]["id"] not in hidden
        and start_ms(lesson["occurrence"]["dateEpochDay"], lesson["occurrence"]["startTimeMinutes"]) > now
    ]
    return {
        "month": anchor.isoformat(),
        "monthLabel": f"{MONTHS_FULL[anchor.month - 1]} {anchor.year}",
        "stats": {
            "studentCount": student_count,
            "studentCount": student_count,
            "weekly": {
                "conducted": sum(1 for o in week_active if o["status"] == STATUS_CONDUCTED),
                "total": len(week_active),
            },
            "monthly": compute_monthly_stats(month_rows),
        },
        "ongoing": ongoing,
        "needsStatus": needs_status,
        "needsStatus": needs_status,
        "upcoming": upcoming_filtered,
        "nowMillis": now,
    }


def _active_others(conn, epoch_day: int, exclude_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT lo.* FROM lesson_occurrences lo
            INNER JOIN students s ON s.id = lo.studentId
            WHERE lo.dateEpochDay = ? AND lo.status != 'CANCELLED' AND lo.id != ? AND s.isArchived = 0
            """,
            (epoch_day, exclude_id),
        )
    ]


def _ensure_no_conflict(candidate: dict, others: list[dict]) -> None:
    if candidate.get("status") == STATUS_CANCELLED:
        return
    start = candidate["startTimeMinutes"]
    end = start + candidate["durationMinutes"]
    for other in others:
        if other["id"] == candidate.get("id") or other["status"] == STATUS_CANCELLED:
            continue
        if other["dateEpochDay"] != candidate["dateEpochDay"]:
            continue
        other_end = other["startTimeMinutes"] + other["durationMinutes"]
        if start < other_end and end > other["startTimeMinutes"]:
            raise ConflictError()


def _from_series(series: dict, on_date: date, price: float) -> dict:
    return {
        "seriesId": series["id"],
        "studentId": series["studentId"],
        "studentSubjectId": series["studentSubjectId"],
        "price": price,
        "dateEpochDay": to_epoch_day(on_date),
        "startTimeMinutes": series["startTimeMinutes"],
        "durationMinutes": series["durationMinutes"],
        "locationType": series["locationType"],
        "address": series["address"],
        "status": STATUS_EXPECTED,
        "reminderMinutes": series["reminderMinutes"],
        "notes": "",
        "paidAmount": 0.0,
    }


def _weekly_occurrences(series: dict, price: float) -> list[dict]:
    end_date = from_epoch_day(series["endDateEpochDay"])
    start = from_epoch_day(series["singleDateEpochDay"]) if series["singleDateEpochDay"] is not None else today()
    current = start
    for _ in range(7):
        if weekday_number(current) == series["dayOfWeek"]:
            break
        current += timedelta(days=1)
    result = []
    while current <= end_date:
        result.append(_from_series(series, current, price))
        current += timedelta(days=7)
    return result


def _insert_occurrence(conn, occ: dict) -> int:
    cur = conn.execute(
        """
        INSERT INTO lesson_occurrences (
            seriesId, studentId, studentSubjectId, price, dateEpochDay,
            startTimeMinutes, durationMinutes, locationType, address,
            status, reminderMinutes, notes, paidAmount
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            occ["seriesId"], occ["studentId"], occ["studentSubjectId"], occ["price"], occ["dateEpochDay"],
            occ["startTimeMinutes"], occ["durationMinutes"], occ["locationType"], occ["address"],
            occ.get("status", STATUS_EXPECTED), occ["reminderMinutes"], occ.get("notes", ""),
            occ.get("paidAmount", 0.0),
        ),
    )
    return int(cur.lastrowid)


def create_lesson(payload: dict) -> int:
    student_id = int(payload["studentId"])
    subject_id = int(payload["studentSubjectId"])
    start_date = parse_iso_date(payload["date"])
    start_time = int(payload["startTimeMinutes"])
    duration = int(payload["durationMinutes"])
    is_weekly = bool(payload.get("isWeekly"))
    end_date = parse_iso_date(payload["endDate"]) if payload.get("endDate") else start_date
    location = payload.get("locationType") or LOCATION_ONLINE
    address = (payload.get("address") or "").strip() or None
    reminder = payload.get("reminderMinutes")
    if is_weekly and end_date < start_date:
        raise AppError("Дата окончания серии не может быть раньше даты начала")
    with db_cursor(transaction=True) as conn:
        subject = as_dict(conn.execute("SELECT * FROM student_subjects WHERE id = ?", (subject_id,)).fetchone())
        if subject is None:
            raise AppError("Предмет не найден")
        if subject["studentId"] != student_id:
            raise AppError("Предмет не принадлежит ученику")
        cur = conn.execute(
            """
            INSERT INTO lesson_series (
                studentId, studentSubjectId, dayOfWeek, startTimeMinutes, durationMinutes,
                isWeekly, endDateEpochDay, singleDateEpochDay, locationType, address, reminderMinutes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                student_id, subject_id, weekday_number(start_date), start_time, duration,
                1 if is_weekly else 0, to_epoch_day(end_date), to_epoch_day(start_date),
                location, address, reminder,
            ),
        )
        series_id = int(cur.lastrowid)
        series = {
            "id": series_id,
            "studentId": student_id,
            "studentSubjectId": subject_id,
            "dayOfWeek": weekday_number(start_date),
            "startTimeMinutes": start_time,
            "durationMinutes": duration,
            "isWeekly": is_weekly,
            "endDateEpochDay": to_epoch_day(end_date),
            "singleDateEpochDay": to_epoch_day(start_date),
            "locationType": location,
            "address": address,
            "reminderMinutes": reminder,
        }
        occurrences = _weekly_occurrences(series, subject["price"]) if is_weekly else [
            _from_series(series, start_date, subject["price"])
        ]
        if not occurrences:
            conn.execute("DELETE FROM lesson_series WHERE id = ?", (series_id,))
            raise AppError("Не удалось создать занятия для указанного периода")
        for occ in occurrences:
            _ensure_no_conflict(occ, _active_others(conn, occ["dateEpochDay"], 0))
            _insert_occurrence(conn, occ)
        return series_id


def change_status(occurrence_id: int, new_status: str) -> None:
    if new_status not in (STATUS_EXPECTED, STATUS_CONDUCTED, STATUS_CANCELLED):
        raise AppError("Некорректный статус")
    with db_cursor(transaction=True) as conn:
        occ = as_dict(conn.execute("SELECT * FROM lesson_occurrences WHERE id = ?", (occurrence_id,)).fetchone())
        if occ is None:
            raise AppError("Занятие не найдено", 404)
        if occ["status"] == new_status:
            return
        if new_status != STATUS_CANCELLED:
            _ensure_no_conflict({**occ, "status": new_status}, _active_others(conn, occ["dateEpochDay"], occ["id"]))
        affecting = occ["status"] == STATUS_CONDUCTED or new_status == STATUS_CONDUCTED
        if occ["status"] == STATUS_CONDUCTED and new_status != STATUS_CONDUCTED:
            _release_payment(conn, occurrence_id)
        paid = occ["paidAmount"] if new_status == STATUS_CONDUCTED else 0.0
        conn.execute(
            "UPDATE lesson_occurrences SET status = ?, paidAmount = ? WHERE id = ?",
            (new_status, paid, occurrence_id),
        )
        if affecting:
            _apply_credit(conn, occ["studentId"])


def reschedule_occurrence(occurrence_id: int, payload: dict) -> None:
    new_date = parse_iso_date(payload["date"])
    with db_cursor(transaction=True) as conn:
        occ = as_dict(conn.execute("SELECT * FROM lesson_occurrences WHERE id = ?", (occurrence_id,)).fetchone())
        if occ is None:
            raise AppError("Занятие не найдено", 404)
        updated = {
            **occ,
            "dateEpochDay": to_epoch_day(new_date),
            "startTimeMinutes": int(payload["startTimeMinutes"]),
            "durationMinutes": int(payload["durationMinutes"]),
            "locationType": payload.get("locationType") or occ["locationType"],
            "address": (payload.get("address") or "").strip() or None,
        }
        _ensure_no_conflict(updated, _active_others(conn, updated["dateEpochDay"], occ["id"]))
        conn.execute(
            """
            UPDATE lesson_occurrences
            SET dateEpochDay = ?, startTimeMinutes = ?, durationMinutes = ?, locationType = ?, address = ?
            WHERE id = ?
            """,
            (
                updated["dateEpochDay"], updated["startTimeMinutes"], updated["durationMinutes"],
                updated["locationType"], updated["address"], occurrence_id,
            ),
        )


def update_notes(occurrence_id: int, notes: str) -> None:
    with db_cursor(transaction=True) as conn:
        conn.execute("UPDATE lesson_occurrences SET notes = ? WHERE id = ?", (notes or "", occurrence_id))


def update_reminder(occurrence_id: int, reminder_minutes: int | None) -> None:
    with db_cursor(transaction=True) as conn:
        conn.execute(
            "UPDATE lesson_occurrences SET reminderMinutes = ? WHERE id = ?",
            (reminder_minutes, occurrence_id),
        )


def change_subject(occurrence_id: int, subject_id: int, apply_to_future: bool = False) -> None:
    with db_cursor(transaction=True) as conn:
        occ = as_dict(conn.execute("SELECT * FROM lesson_occurrences WHERE id = ?", (occurrence_id,)).fetchone())
        if occ is None:
            raise AppError("Занятие не найдено", 404)
        subject = as_dict(conn.execute("SELECT * FROM student_subjects WHERE id = ?", (subject_id,)).fetchone())
        if subject is None:
            raise AppError("Предмет не найден")
        if subject["studentId"] != occ["studentId"]:
            raise AppError("Предмет не принадлежит ученику")
        if occ["studentSubjectId"] == subject_id and abs(occ["price"] - subject["price"]) < 0.001:
            return
        conn.execute(
            "UPDATE lesson_occurrences SET studentSubjectId = ?, price = ? WHERE id = ?",
            (subject_id, subject["price"], occurrence_id),
        )
        if apply_to_future:
            conn.execute("UPDATE lesson_series SET studentSubjectId = ? WHERE id = ?", (subject_id, occ["seriesId"]))
            future = conn.execute(
                """
                SELECT id FROM lesson_occurrences
                WHERE seriesId = ? AND status = 'EXPECTED' AND dateEpochDay >= ? AND id != ?
                """,
                (occ["seriesId"], occ["dateEpochDay"], occ["id"]),
            )
            for row in future:
                conn.execute(
                    "UPDATE lesson_occurrences SET studentSubjectId = ?, price = ? WHERE id = ?",
                    (subject_id, subject["price"], row["id"]),
                )
        if occ["status"] == STATUS_CONDUCTED:
            _rebalance_payments(conn, occ["studentId"])


def _next_date_for_weekday(day_of_week: int, from_date: date) -> date:
    current = from_date
    for _ in range(7):
        if weekday_number(current) == day_of_week:
            return current
        current += timedelta(days=1)
    return from_date


def update_series_future(series_id: int, payload: dict) -> None:
    with db_cursor(transaction=True) as conn:
        series = as_dict(conn.execute("SELECT * FROM lesson_series WHERE id = ?", (series_id,)).fetchone())
        if series is None:
            raise AppError("Серия не найдена", 404)
        start_time = int(payload["startTimeMinutes"])
        duration = int(payload["durationMinutes"])
        location = payload.get("locationType") or series["locationType"]
        address = (payload.get("address") or "").strip() or None
        reminder = payload.get("reminderMinutes")
        old_dow = int(series["dayOfWeek"])
        if payload.get("dayOfWeek") is None:
            dow = old_dow
        else:
            dow = int(payload["dayOfWeek"])
        if dow not in range(1, 8):
            raise AppError("Некорректный день недели")
        delta = (dow - old_dow) % 7

        updates = []
        for row in conn.execute("SELECT * FROM lesson_occurrences WHERE seriesId = ?", (series_id,)):
            if row["status"] != STATUS_EXPECTED:
                continue
            updated = dict(row)
            updated.update(
                {
                    "dateEpochDay": int(row["dateEpochDay"]) + delta,
                    "startTimeMinutes": start_time,
                    "durationMinutes": duration,
                    "locationType": location,
                    "address": address,
                    "reminderMinutes": reminder,
                }
            )
            updates.append(updated)

        moving_ids = {item["id"] for item in updates}
        for updated in updates:
            db_others = [
                other
                for other in _active_others(conn, updated["dateEpochDay"], updated["id"])
                if other["id"] not in moving_ids
            ]
            siblings = [other for other in updates if other["id"] != updated["id"]]
            _ensure_no_conflict(updated, db_others + siblings)

        for updated in updates:
            conn.execute(
                """
                UPDATE lesson_occurrences
                SET dateEpochDay = ?, startTimeMinutes = ?, durationMinutes = ?,
                    locationType = ?, address = ?, reminderMinutes = ?
                WHERE id = ?
                """,
                (
                    updated["dateEpochDay"],
                    start_time,
                    duration,
                    location,
                    address,
                    reminder,
                    updated["id"],
                ),
            )

        new_end = int(series["endDateEpochDay"])
        if updates:
            new_end = max(new_end, max(item["dateEpochDay"] for item in updates))

        new_single = series["singleDateEpochDay"]
        if delta:
            if updates:
                new_single = min(item["dateEpochDay"] for item in updates)
            else:
                new_single = to_epoch_day(_next_date_for_weekday(dow, today()))

        conn.execute(
            """
            UPDATE lesson_series
            SET dayOfWeek = ?, startTimeMinutes = ?, durationMinutes = ?,
                locationType = ?, address = ?, reminderMinutes = ?,
                endDateEpochDay = ?, singleDateEpochDay = ?
            WHERE id = ?
            """,
            (dow, start_time, duration, location, address, reminder, new_end, new_single, series_id),
        )


def extend_series(series_id: int, new_end_iso: str) -> None:
    new_end_epoch = to_epoch_day(parse_iso_date(new_end_iso))
    with db_cursor(transaction=True) as conn:
        series = as_dict(conn.execute("SELECT * FROM lesson_series WHERE id = ?", (series_id,)).fetchone())
        if series is None or not series["isWeekly"]:
            return
        subject = as_dict(
            conn.execute("SELECT * FROM student_subjects WHERE id = ?", (series["studentSubjectId"],)).fetchone()
        )
        if subject is None:
            raise AppError("Предмет серии не найден")
        conn.execute("UPDATE lesson_series SET endDateEpochDay = ? WHERE id = ?", (new_end_epoch, series_id))
        conn.execute(
            "DELETE FROM lesson_occurrences WHERE seriesId = ? AND status = 'EXPECTED' AND dateEpochDay > ?",
            (series_id, new_end_epoch),
        )
        existing = {
            r[0] for r in conn.execute("SELECT dateEpochDay FROM lesson_occurrences WHERE seriesId = ?", (series_id,))
        }
        series["endDateEpochDay"] = new_end_epoch
        for occ in _weekly_occurrences(series, subject["price"]):
            if occ["dateEpochDay"] in existing:
                continue
            _ensure_no_conflict(occ, _active_others(conn, occ["dateEpochDay"], 0))
            _insert_occurrence(conn, occ)


def delete_occurrence(occurrence_id: int) -> None:
    with db_cursor(transaction=True) as conn:
        occ = as_dict(conn.execute("SELECT * FROM lesson_occurrences WHERE id = ?", (occurrence_id,)).fetchone())
        if occ is None:
            return
        was_conducted = occ["status"] == STATUS_CONDUCTED
        if was_conducted:
            _release_payment(conn, occurrence_id)
        conn.execute("DELETE FROM lesson_occurrences WHERE id = ?", (occurrence_id,))
        remaining = conn.execute(
            "SELECT COUNT(*) FROM lesson_occurrences WHERE seriesId = ?", (occ["seriesId"],)
        ).fetchone()[0]
        series = as_dict(conn.execute("SELECT * FROM lesson_series WHERE id = ?", (occ["seriesId"],)).fetchone())
        if remaining == 0 or (series and not series["isWeekly"]):
            conn.execute("DELETE FROM lesson_series WHERE id = ?", (occ["seriesId"],))
        if was_conducted:
            _apply_credit(conn, occ["studentId"])


def delete_series(series_id: int) -> None:
    with db_cursor(transaction=True) as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM lesson_occurrences WHERE seriesId = ?", (series_id,))]
        if not rows:
            return
        student_id = rows[0]["studentId"]
        needs = any(r["status"] == STATUS_CONDUCTED for r in rows)
        for row in rows:
            if row["status"] == STATUS_CONDUCTED:
                _release_payment(conn, row["id"])
        conn.execute("DELETE FROM lesson_occurrences WHERE seriesId = ?", (series_id,))
        conn.execute("DELETE FROM lesson_series WHERE id = ?", (series_id,))
        if needs:
            _apply_credit(conn, student_id)


def _student_balance(conn, student_id: int) -> float:
    paid = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE studentId = ?", (student_id,)
    ).fetchone()[0]
    allocated = conn.execute(
        """
        SELECT COALESCE(SUM(pa.amount), 0) FROM payment_allocations pa
        INNER JOIN lesson_occurrences lo ON lo.id = pa.occurrenceId
        WHERE lo.studentId = ?
        """,
        (student_id,),
    ).fetchone()[0]
    return paid - allocated


def student_balance(student_id: int) -> float:
    with db_cursor() as conn:
        return _student_balance(conn, student_id)


def process_payment(student_id: int, amount: float, note: str = "") -> int:
    if amount <= 0.001:
        raise AppError("Сумма платежа должна быть больше нуля")
    with db_cursor(transaction=True) as conn:
        if conn.execute("SELECT id FROM students WHERE id = ?", (student_id,)).fetchone() is None:
            raise AppError("Ученик не найден", 404)
        cur = conn.execute(
            "INSERT INTO payments (studentId, amount, createdAt, note) VALUES (?, ?, ?, ?)",
            (student_id, amount, now_ms(), note or ""),
        )
        _apply_credit(conn, student_id)
        return int(cur.lastrowid)


def delete_payment(payment_id: int) -> None:
    with db_cursor(transaction=True) as conn:
        payment = as_dict(conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone())
        if payment is None:
            return
        for alloc in conn.execute("SELECT * FROM payment_allocations WHERE paymentId = ?", (payment_id,)):
            occ = as_dict(
                conn.execute("SELECT * FROM lesson_occurrences WHERE id = ?", (alloc["occurrenceId"],)).fetchone()
            )
            if occ is None:
                continue
            conn.execute(
                "UPDATE lesson_occurrences SET paidAmount = ? WHERE id = ?",
                (max(occ["paidAmount"] - alloc["amount"], 0.0), occ["id"]),
            )
        conn.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
        _apply_credit(conn, payment["studentId"])


def list_payments() -> list[dict]:
    with db_cursor() as conn:
        students = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM students")}
        result = []
        for row in conn.execute("SELECT * FROM payments ORDER BY createdAt DESC"):
            payment = dict(row)
            student = students.get(payment["studentId"])
            result.append(
                {
                    "payment": payment,
                    "student": {**student, "isArchived": bool(student["isArchived"])} if student else None,
                }
            )
        return result


def list_unpaid_students() -> list[dict]:
    with db_cursor() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT lo.*, ss.name AS subjectName
                FROM lesson_occurrences lo
                LEFT JOIN student_subjects ss ON ss.id = lo.studentSubjectId
                WHERE lo.status = ?
                  AND (lo.price - lo.paidAmount) > 0.001
                ORDER BY lo.dateEpochDay ASC, lo.startTimeMinutes ASC
                """,
                (STATUS_CONDUCTED,),
            )
        ]
        if not rows:
            return []
        student_ids = sorted({int(r["studentId"]) for r in rows})
        placeholders = ",".join("?" * len(student_ids))
        students = [
            dict(r)
            for r in conn.execute(
                f"SELECT * FROM students WHERE id IN ({placeholders})",
                student_ids,
            )
        ]
        subjects = [dict(r) for r in conn.execute("SELECT * FROM student_subjects")]
        student_map = {s["id"]: s for s in with_subjects(students, subjects)}
        grouped: dict[int, list[dict]] = {}
        for occ in rows:
            grouped.setdefault(int(occ["studentId"]), []).append(occ)
        result = []
        for student_id, lessons in grouped.items():
            student = student_map.get(student_id)
            if student is None:
                continue
            unpaid_amount = sum(max(float(lesson["price"]) - float(lesson["paidAmount"]), 0.0) for lesson in lessons)
            result.append(
                {
                    "student": student,
                    "unpaidAmount": unpaid_amount,
                    "unpaidLessonsCount": len(lessons),
                    "oldestUnpaidDateEpochDay": min(int(lesson["dateEpochDay"]) for lesson in lessons),
                    "lessons": [
                        {
                            "id": lesson["id"],
                            "dateEpochDay": lesson["dateEpochDay"],
                            "startTimeMinutes": lesson["startTimeMinutes"],
                            "durationMinutes": lesson["durationMinutes"],
                            "price": lesson["price"],
                            "paidAmount": lesson["paidAmount"],
                            "unpaidAmount": max(float(lesson["price"]) - float(lesson["paidAmount"]), 0.0),
                            "subjectName": (str(lesson.get("subjectName") or "").strip() or "Предмет"),
                        }
                        for lesson in lessons
                    ],
                }
            )
        result.sort(key=lambda item: (-item["unpaidAmount"], item["student"]["name"].lower()))
        return result


def student_detail(student_id: int, month_iso: str | None = None) -> dict:
    anchor = parse_iso_date(month_iso) if month_iso else today()
    month_from, month_to = month_bounds(anchor)
    student = get_student(student_id)
    with db_cursor() as conn:
        lessons = [
            dict(r)
            for r in conn.execute(
                """
                SELECT * FROM lesson_occurrences
                WHERE studentId = ? AND dateEpochDay BETWEEN ? AND ?
                ORDER BY dateEpochDay, startTimeMinutes
                """,
                (student_id, month_from, month_to),
            )
        ]
        payments = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM payments WHERE studentId = ? ORDER BY createdAt DESC", (student_id,)
            )
        ]
        balance = _student_balance(conn, student_id)
    subjects = {s["id"]: s for s in student["subjects"]}
    lesson_items = [
        {**occ, "subjectName": subjects.get(occ["studentSubjectId"], {}).get("name", "Предмет")}
        for occ in lessons
    ]
    return {
        "student": student,
        "month": anchor.isoformat(),
        "monthLabel": f"{MONTHS_FULL[anchor.month - 1]} {anchor.year}",
        "stats": compute_monthly_stats(lessons),
        "lessons": lesson_items,
        "payments": payments,
        "balance": balance,
    }


def _preview(notes: str) -> str:
    collapsed = " ".join((notes or "").split())
    return collapsed if len(collapsed) <= 90 else collapsed[:90].rstrip() + "…"


def journal_summaries() -> list[dict]:
    students = list_students(archived=False)
    today_day = to_epoch_day(today())
    with db_cursor() as conn:
        occurrences = [dict(r) for r in conn.execute("SELECT * FROM lesson_occurrences")]
    by_student: dict[int, list[dict]] = {}
    for occ in occurrences:
        by_student.setdefault(occ["studentId"], []).append(occ)
    result = []
    for student in students:
        lessons = by_student.get(student["id"], [])
        with_notes = [o for o in lessons if (o["notes"] or "").strip()]
        last = max(with_notes, key=lambda o: (o["dateEpochDay"], o["startTimeMinutes"]), default=None)
        result.append(
            {
                "student": student,
                "lastNoteDateEpochDay": last["dateEpochDay"] if last else None,
                "lastNotePreview": _preview(last["notes"]) if last else "",
                "missingNotesCount": sum(
                    1 for o in lessons if o["status"] == STATUS_CONDUCTED and not (o["notes"] or "").strip()
                ),
                "upcomingCount": sum(
                    1 for o in lessons if o["status"] == STATUS_EXPECTED and o["dateEpochDay"] >= today_day
                ),
            }
        )
    return result


def student_journal(student_id: int) -> dict:
    today_day = to_epoch_day(today())
    with db_cursor() as conn:
        student = as_dict(conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone())
        if student is None:
            raise AppError("Ученик не найден", 404)
        subjects = {s["id"]: s for s in load_subjects(conn, student_id)}
        occurrences = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM lesson_occurrences WHERE studentId = ? ORDER BY dateEpochDay, startTimeMinutes",
                (student_id,),
            )
        ]

    def to_item(occ: dict) -> dict:
        subject = subjects.get(occ["studentSubjectId"])
        notes = occ["notes"] or ""
        return {
            "occurrence": occ,
            "subjectName": subject["name"] if subject and str(subject["name"]).strip() else "Предмет",
            "hasNotes": bool(notes.strip()),
            "preview": _preview(notes),
        }

    upcoming = [
        to_item(o)
        for o in occurrences
        if o["status"] == STATUS_EXPECTED and o["dateEpochDay"] >= today_day
    ]
    conducted = [
        to_item(o)
        for o in sorted(
            (o for o in occurrences if o["status"] == STATUS_CONDUCTED),
            key=lambda o: (o["dateEpochDay"], o["startTimeMinutes"]),
            reverse=True,
        )
    ]
    student["isArchived"] = bool(student["isArchived"])
    return {"student": student, "upcoming": upcoming, "conducted": conducted}


def get_settings() -> dict:
    with db_cursor() as conn:
        row = as_dict(conn.execute("SELECT * FROM app_settings WHERE id = 1").fetchone())
        if row is None:
            raise AppError("Настройки не найдены", 404)
        main = str(row.get("telegramChatId") or "").strip()
        extra = []
        for item in str(row["dailyScheduleExtraChatIds"] or "").replace(",", "\n").replace(";", "\n").split("\n"):
            value = item.strip()
            if value and value != main and value not in extra:
                extra.append(value)
        row["notificationsEnabled"] = bool(row["notificationsEnabled"])
        row["dailyScheduleEnabled"] = bool(row["dailyScheduleEnabled"])
        row["extraChatIds"] = extra
        return row


def update_settings(payload: dict) -> dict:
    current = get_settings()
    current.update(payload)
    extra = None
    for key, value in payload.items():
        compact = key.replace("_", "").lower()
        if compact in {"extrachatids", "dailyscheduleextrachatids"}:
            extra = value
            break
    if extra is None:
        extra = current.get("extraChatIds")
    if extra is not None:
        if isinstance(extra, str):
            items = extra.replace(",", "\n").replace(";", "\n").split("\n")
        elif isinstance(extra, (list, tuple, set)):
            items = extra
        else:
            items = [extra]
        main = str(current.get("telegramChatId") or "").strip()
        seen: list[str] = []
        for item in items:
            value = str(item).strip()
            if value and value != main and value not in seen:
                seen.append(value)
        current["dailyScheduleExtraChatIds"] = "\n".join(seen)
    minutes = max(int(current.get("globalReminderMinutes") or 30), 1)
    daily = min(max(int(current.get("dailyScheduleMinutes") or 420), 0), 23 * 60 + 59)
    with db_cursor(transaction=True) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO app_settings (
                id, globalReminderMinutes, notificationsEnabled, themeMode,
                telegramBotToken, telegramChatId, dailyScheduleEnabled,
                dailyScheduleMinutes, dailyScheduleExtraChatIds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                minutes,
                1 if current.get("notificationsEnabled", True) else 0,
                current.get("themeMode") or "SYSTEM",
                (current.get("telegramBotToken") or "").strip(),
                (current.get("telegramChatId") or "").strip(),
                1 if current.get("dailyScheduleEnabled", True) else 0,
                daily,
                current.get("dailyScheduleExtraChatIds") or "",
            ),
        )
    return get_settings()


def _release_payment(conn, occurrence_id: int) -> None:
    conn.execute("DELETE FROM payment_allocations WHERE occurrenceId = ?", (occurrence_id,))
    conn.execute("UPDATE lesson_occurrences SET paidAmount = 0 WHERE id = ?", (occurrence_id,))


def _rebalance_payments(conn, student_id: int) -> None:
    for occ in conn.execute(
        "SELECT id FROM lesson_occurrences WHERE studentId = ? AND status = 'CONDUCTED'",
        (student_id,),
    ):
        conn.execute("DELETE FROM payment_allocations WHERE occurrenceId = ?", (occ["id"],))
        conn.execute("UPDATE lesson_occurrences SET paidAmount = 0 WHERE id = ?", (occ["id"],))
    _apply_credit(conn, student_id)


def _apply_credit(conn, student_id: int) -> None:
    if conn.execute("SELECT id FROM students WHERE id = ?", (student_id,)).fetchone() is None:
        return
    balance = _student_balance(conn, student_id)
    if balance <= 0.001:
        return
    conducted = [
        dict(r)
        for r in conn.execute(
            """
            SELECT * FROM lesson_occurrences
            WHERE studentId = ? AND status = 'CONDUCTED'
            ORDER BY dateEpochDay, startTimeMinutes
            """,
            (student_id,),
        )
    ]
    paid_map = {occ["id"]: occ["paidAmount"] for occ in conducted}
    payments = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM payments WHERE studentId = ? ORDER BY createdAt ASC", (student_id,)
        )
    ]
    remaining = {}
    for payment in payments:
        allocated = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payment_allocations WHERE paymentId = ?",
            (payment["id"],),
        ).fetchone()[0]
        remaining[payment["id"]] = payment["amount"] - allocated
    allocations = []
    for occ in conducted:
        needed = occ["price"] - paid_map[occ["id"]]
        if needed <= 0.001:
            continue
        for payment in payments:
            if needed <= 0.001 or balance <= 0.001:
                break
            left = remaining.get(payment["id"], 0.0)
            if left <= 0.001:
                continue
            allocate = min(needed, left, balance)
            if allocate <= 0.001:
                continue
            allocations.append((payment["id"], occ["id"], allocate))
            new_paid = paid_map[occ["id"]] + allocate
            paid_map[occ["id"]] = new_paid
            conn.execute("UPDATE lesson_occurrences SET paidAmount = ? WHERE id = ?", (new_paid, occ["id"]))
            remaining[payment["id"]] = left - allocate
            balance -= allocate
            needed -= allocate
    for payment_id, occurrence_id, amount in allocations:
        conn.execute(
            "INSERT INTO payment_allocations (paymentId, occurrenceId, amount) VALUES (?, ?, ?)",
            (payment_id, occurrence_id, amount),
        )


def format_today_schedule_html() -> str:
    day = today()
    lessons = lessons_in_range(to_epoch_day(day), to_epoch_day(day))

    def occ_of(lesson: dict) -> dict:
        return lesson.get("occurrence") or lesson.get("occurrence") or {}

    def student_of(lesson: dict) -> dict:
        return lesson.get("student") or {}

    active = [
        lesson
        for lesson in lessons
        if occ_of(lesson).get("status") != STATUS_CANCELLED
        and not bool(student_of(lesson).get("isArchived") or student_of(lesson).get("isArchived"))
    ]
    active.sort(key=lambda item: int(occ_of(item).get("startTimeMinutes") or occ_of(item).get("startTimeMinutes") or 0))
    title = f"📅 Расписание на {day.day} {MONTHS_SHORT[day.month - 1]} {day.year}"

    def esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    if not active:
        return f"<b>{esc(title)}</b>\n\nНа сегодня занятий нет."
    blocks = []
    for lesson in active:
        occ = occ_of(lesson)
        start = int(occ.get("startTimeMinutes") or occ.get("startTimeMinutes") or 0)
        time_label = f"{start // 60:02d}:{start % 60:02d}"
        location = occ.get("locationType") or occ.get("locationType")
        place = (
            "Онлайн"
            if location == LOCATION_ONLINE
            else (occ.get("address") or student_of(lesson).get("address") or "Офлайн")
        )
        blocks.append(
            f"<b>{esc(time_label)}</b> · {esc(lesson['subjectName'])}\n"
            f"👤 {esc(lesson['student']['name'])}\n"
            f"📍 {esc(place)}"
        )
    body = "\n————————————\n".join(blocks)
    return f"<b>{esc(title)}</b>\n\n{body}\n\nЗанятий: {len(active)}"


def _bind_aliases(*pairs: tuple[str, str]) -> None:
    g = globals()
    for left, right in pairs:
        if left in g and right not in g:
            g[right] = g[left]
        elif right in g and left not in g:
            g[left] = g[right]


_bind_aliases(
    ("list_students", "list_students"),
    ("add_student", "add_student"),
    ("student_detail", "student_detail"),
    ("set_student_archived", "set_student_archived"),
    ("lessons_in_range", "lessons_in_range"),
    ("get_lesson", "get_lesson"),
    ("get_series", "get_series"),
    ("change_status", "change_status"),
    ("reschedule_occurrence", "reschedule_occurrence"),
    ("update_series_future", "update_series_future"),
    ("extend_series", "extend_series"),
    ("delete_occurrence", "delete_occurrence"),
    ("journal_summaries", "journal_summaries"),
    ("student_journal", "student_journal"),
    ("list_payments", "list_payments"),
    ("list_unpaid_students", "list_unpaid_students"),
    ("process_payment", "process_payment"),
    ("get_settings", "get_settings"),
    ("update_settings", "update_settings"),
    ("to_epoch_day", "to_epoch_day"),
    ("from_epoch_day", "from_epoch_day"),
    ("week_bounds", "week_bounds"),
    ("format_today_schedule_html", "format_today_schedule_html"),
    ("AppError", "AppError"),
    ("ConflictError", "ConflictError"),
    ("as_dict", "as_dict"),
)
