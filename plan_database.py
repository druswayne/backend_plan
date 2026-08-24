"""Отдельная SQLite-база совместного планирования. Не связана с ClassHub."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager

from database import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "plan.db")

_lock = threading.RLock()
_connection: sqlite3.Connection | None = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    event_date TEXT NOT NULL,
    event_time TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL DEFAULT 60,
    importance TEXT NOT NULL,
    author TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plan_events_date ON events (event_date);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY NOT NULL,
    reminder_minutes INTEGER NOT NULL DEFAULT 30,
    notifications_enabled INTEGER NOT NULL DEFAULT 1,
    telegram_bot_token TEXT NOT NULL DEFAULT '',
    telegram_chat_ids TEXT NOT NULL DEFAULT '',
    daily_enabled INTEGER NOT NULL DEFAULT 0,
    daily_minutes INTEGER NOT NULL DEFAULT 420
);
INSERT OR IGNORE INTO settings (id) VALUES (1);
"""


def init_db() -> None:
    global _connection
    os.makedirs(DATA_DIR, exist_ok=True)
    with _lock:
        if _connection is None:
            conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            _connection = conn
        _connection.executescript(SCHEMA_SQL)
        _connection.commit()


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
