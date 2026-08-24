"""SQLite-схема, совместимая с Room AppDatabase (version 8)."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager

ROOM_IDENTITY_HASH = "1496f104654ba8e4ebfe2317fb58fe6b"
ROOM_VERSION = 8

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "repik.db")

REQUIRED_TABLES = (
    "students",
    "student_subjects",
    "lesson_series",
    "lesson_occurrences",
    "payments",
    "payment_allocations",
    "app_settings",
)

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS `students` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    `name` TEXT NOT NULL,
    `grade` TEXT NOT NULL,
    `address` TEXT,
    `isArchived` INTEGER NOT NULL,
    `createdAt` INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS `student_subjects` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    `studentId` INTEGER NOT NULL,
    `name` TEXT NOT NULL,
    `price` REAL NOT NULL,
    FOREIGN KEY(`studentId`) REFERENCES `students`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS `index_student_subjects_studentId` ON `student_subjects` (`studentId`);

CREATE TABLE IF NOT EXISTS `lesson_series` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    `studentId` INTEGER NOT NULL,
    `studentSubjectId` INTEGER NOT NULL,
    `dayOfWeek` INTEGER NOT NULL,
    `startTimeMinutes` INTEGER NOT NULL,
    `durationMinutes` INTEGER NOT NULL,
    `isWeekly` INTEGER NOT NULL,
    `endDateEpochDay` INTEGER NOT NULL,
    `singleDateEpochDay` INTEGER,
    `locationType` TEXT NOT NULL,
    `address` TEXT,
    `reminderMinutes` INTEGER,
    FOREIGN KEY(`studentId`) REFERENCES `students`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE,
    FOREIGN KEY(`studentSubjectId`) REFERENCES `student_subjects`(`id`) ON UPDATE NO ACTION ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS `index_lesson_series_studentId` ON `lesson_series` (`studentId`);
CREATE INDEX IF NOT EXISTS `index_lesson_series_studentSubjectId` ON `lesson_series` (`studentSubjectId`);

CREATE TABLE IF NOT EXISTS `lesson_occurrences` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    `seriesId` INTEGER NOT NULL,
    `studentId` INTEGER NOT NULL,
    `studentSubjectId` INTEGER NOT NULL,
    `price` REAL NOT NULL,
    `dateEpochDay` INTEGER NOT NULL,
    `startTimeMinutes` INTEGER NOT NULL,
    `durationMinutes` INTEGER NOT NULL,
    `locationType` TEXT NOT NULL,
    `address` TEXT,
    `status` TEXT NOT NULL,
    `reminderMinutes` INTEGER,
    `notes` TEXT NOT NULL,
    `paidAmount` REAL NOT NULL,
    FOREIGN KEY(`studentId`) REFERENCES `students`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE,
    FOREIGN KEY(`seriesId`) REFERENCES `lesson_series`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE,
    FOREIGN KEY(`studentSubjectId`) REFERENCES `student_subjects`(`id`) ON UPDATE NO ACTION ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS `index_lesson_occurrences_studentId` ON `lesson_occurrences` (`studentId`);
CREATE INDEX IF NOT EXISTS `index_lesson_occurrences_seriesId` ON `lesson_occurrences` (`seriesId`);
CREATE INDEX IF NOT EXISTS `index_lesson_occurrences_dateEpochDay` ON `lesson_occurrences` (`dateEpochDay`);
CREATE INDEX IF NOT EXISTS `index_lesson_occurrences_studentSubjectId` ON `lesson_occurrences` (`studentSubjectId`);

CREATE TABLE IF NOT EXISTS `payments` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    `studentId` INTEGER NOT NULL,
    `amount` REAL NOT NULL,
    `createdAt` INTEGER NOT NULL,
    `note` TEXT NOT NULL,
    FOREIGN KEY(`studentId`) REFERENCES `students`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS `index_payments_studentId` ON `payments` (`studentId`);

CREATE TABLE IF NOT EXISTS `payment_allocations` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    `paymentId` INTEGER NOT NULL,
    `occurrenceId` INTEGER NOT NULL,
    `amount` REAL NOT NULL,
    FOREIGN KEY(`paymentId`) REFERENCES `payments`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE,
    FOREIGN KEY(`occurrenceId`) REFERENCES `lesson_occurrences`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS `index_payment_allocations_paymentId` ON `payment_allocations` (`paymentId`);
CREATE INDEX IF NOT EXISTS `index_payment_allocations_occurrenceId` ON `payment_allocations` (`occurrenceId`);

CREATE TABLE IF NOT EXISTS `app_settings` (
    `id` INTEGER NOT NULL,
    `globalReminderMinutes` INTEGER NOT NULL,
    `notificationsEnabled` INTEGER NOT NULL,
    `themeMode` TEXT NOT NULL,
    `telegramBotToken` TEXT NOT NULL,
    `telegramChatId` TEXT NOT NULL,
    `dailyScheduleEnabled` INTEGER NOT NULL,
    `dailyScheduleMinutes` INTEGER NOT NULL,
    `dailyScheduleExtraChatIds` TEXT NOT NULL,
    PRIMARY KEY(`id`)
);

CREATE TABLE IF NOT EXISTS room_master_table (id INTEGER PRIMARY KEY, identity_hash TEXT);
INSERT OR REPLACE INTO room_master_table (id, identity_hash)
VALUES(42, '{ROOM_IDENTITY_HASH}');
"""

DEFAULT_SETTINGS = {
    "id": 1,
    "globalReminderMinutes": 30,
    "notificationsEnabled": 1,
    "themeMode": "SYSTEM",
    "telegramBotToken": "8917790556:AAGIueKoZWEp3EPI4Mhdd2mc2SvXEzPO8WY",
    "telegramChatId": "731866035",
    "dailyScheduleEnabled": 1,
    "dailyScheduleMinutes": 7 * 60,
    "dailyScheduleExtraChatIds": "",
}

_lock = threading.RLock()
_connection: sqlite3.Connection | None = None


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.execute(f"PRAGMA user_version = {ROOM_VERSION}")
    existing = conn.execute("SELECT id FROM app_settings WHERE id = 1").fetchone()
    if existing is None:
        conn.execute(
            """
            INSERT INTO app_settings (
                id, globalReminderMinutes, notificationsEnabled, themeMode,
                telegramBotToken, telegramChatId, dailyScheduleEnabled,
                dailyScheduleMinutes, dailyScheduleExtraChatIds
            ) VALUES (
                :id, :globalReminderMinutes, :notificationsEnabled, :themeMode,
                :telegramBotToken, :telegramChatId, :dailyScheduleEnabled,
                :dailyScheduleMinutes, :dailyScheduleExtraChatIds
            )
            """,
            DEFAULT_SETTINGS,
        )


def _close_db() -> None:
    global _connection
    conn = _connection
    _connection = None
    if conn is None:
        return
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("PRAGMA journal_mode = DELETE")
    except sqlite3.Error:
        pass
    try:
        conn.close()
    except sqlite3.Error:
        pass


def init_db(path: str | None = None) -> str:
    global _connection
    db_path = path or DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with _lock:
        _close_db()
        conn = _connect(db_path)
        _ensure_schema(conn)
        _connection = conn
    return db_path


def get_connection() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        init_db()
    assert _connection is not None
    return _connection


@contextmanager
def db_cursor(transaction: bool = False):
    with _lock:
        conn = get_connection()
        if transaction:
            conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            if transaction:
                conn.execute("COMMIT")
        except Exception:
            if transaction:
                conn.execute("ROLLBACK")
            raise


def checkpoint() -> None:
    with _lock:
        conn = get_connection()
        conn.execute("PRAGMA wal_checkpoint(FULL)")


def is_valid_repik_database(path: str) -> bool:
    if not os.path.isfile(path) or os.path.getsize(path) < 512:
        return False
    with open(path, "rb") as fh:
        header = fh.read(16)
    if header[:15] != b"SQLite format 3":
        return False
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            return all(table in names for table in REQUIRED_TABLES)
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def replace_database(source_path: str) -> None:
    if not is_valid_repik_database(source_path):
        raise ValueError("Файл не является резервной копией ClassHub")
    with _lock:
        dest = get_connection()
        src = sqlite3.connect(source_path)
        try:
            src.backup(dest)
        finally:
            src.close()
        dest.execute("PRAGMA foreign_keys = ON")
        dest.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        _ensure_schema(dest)


def export_copy(dest_path: str) -> None:
    checkpoint()
    with _lock:
        with open(DB_PATH, "rb") as fh_in, open(dest_path, "wb") as fh_out:
            fh_out.write(fh_in.read())


def _bind_aliases(*pairs: tuple[str, str]) -> None:
    g = globals()
    for left, right in pairs:
        if left in g and right not in g:
            g[right] = g[left]
        elif right in g and left not in g:
            g[left] = g[right]


_bind_aliases(
    ("init_db", "init_db"),
    ("db_cursor", "db_cursor"),
    ("export_copy", "export_copy"),
    ("replace_database", "replace_database"),
    ("is_valid_repik_database", "is_valid_repik_database"),
)
