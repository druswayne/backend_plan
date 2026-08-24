"""Логин и пароль для сайта. Хранятся отдельно от учебной базы."""

from __future__ import annotations

import json
import os
import secrets

from flask import jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import DATA_DIR

AUTH_PATH = os.path.join(DATA_DIR, "site_auth.json")
SECRET_PATH = os.path.join(DATA_DIR, "secret_key")

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"


def ensure_secret_key() -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.isfile(SECRET_PATH):
        return open(SECRET_PATH, encoding="utf-8").read().strip()
    value = secrets.token_hex(32)
    with open(SECRET_PATH, "w", encoding="utf-8") as fh:
        fh.write(value)
    return value


def _dump(payload: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = AUTH_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, AUTH_PATH)


def load_auth() -> dict:
    if not os.path.isfile(AUTH_PATH):
        save_credentials(DEFAULT_USERNAME, DEFAULT_PASSWORD)
    with open(AUTH_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def save_credentials(username: str, password: str) -> None:
    username = (username or "").strip()
    if not username:
        raise ValueError("Укажите логин")
    if not (password or "").strip():
        raise ValueError("Укажите пароль")
    _dump(
        {
            "username": username,
            "password_hash": generate_password_hash(password),
        }
    )


def current_username() -> str:
    return str(load_auth().get("username") or DEFAULT_USERNAME)


def verify_password(username: str, password: str) -> bool:
    stored = load_auth()
    expected_user = str(stored.get("username") or "")
    password_hash = str(stored.get("password_hash") or "")
    if not expected_user or not password_hash:
        return False
    user_ok = secrets.compare_digest(username.strip().encode("utf-8"), expected_user.encode("utf-8"))
    return user_ok and check_password_hash(password_hash, password or "")


def is_authenticated() -> bool:
    if session.get("user"):
        return True
    basic = request.authorization
    if basic and verify_password(basic.username or "", basic.password or ""):
        return True
    return False


def login_user(username: str) -> None:
    session.clear()
    session["user"] = username.strip()
    session.permanent = True


def logout_user() -> None:
    session.clear()


def require_login():
    if request.method == "OPTIONS":
        return None
    path = request.path
    if path in {"/login"} or path.startswith("/static/"):
        return None
    # Совместное планирование — отдельное приложение, без логина ClassHub.
    if path == "/plan" or path.startswith("/plan/") or path.startswith("/api/plan"):
        return None
    if is_authenticated():
        return None
    if path.startswith("/api/"):
        return jsonify({"error": "Нужна авторизация. Войдите на сайт или укажите логин и пароль в приложении."}), 401
    nxt = path if path != "/logout" else "/"
    return redirect(url_for("login", next=nxt))
