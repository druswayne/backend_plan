"""Маршруты совместного планирования. Не пересекаются с API ClassHub."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

import plan_database
import plan_service
import plan_telegram_jobs

bp = Blueprint("plan", __name__)


def _error(exc: Exception, status: int = 400):
    message = getattr(exc, "message", None) or str(exc)
    code = getattr(exc, "status", status)
    return jsonify({"error": message}), code


@bp.get("/plan")
def plan_page():
    return render_template("plan.html")


@bp.get("/api/plan/health")
def plan_health():
    plan_database.init_db()
    return jsonify({"ok": True, "app": "Plan"})


@bp.get("/api/plan/events")
def list_events():
    try:
        return jsonify(plan_service.list_events(request.args.get("from"), request.args.get("to")))
    except plan_service.PlanError as exc:
        return _error(exc)


@bp.post("/api/plan/events")
def create_event():
    data = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(plan_service.create_event(data)), 201
    except plan_service.PlanError as exc:
        return _error(exc)


@bp.get("/api/plan/events/<int:event_id>")
def get_event(event_id: int):
    try:
        return jsonify(plan_service.get_event(event_id))
    except plan_service.PlanError as exc:
        return _error(exc)


@bp.put("/api/plan/events/<int:event_id>")
def update_event(event_id: int):
    data = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(plan_service.update_event(event_id, data))
    except plan_service.PlanError as exc:
        return _error(exc)


@bp.delete("/api/plan/events/<int:event_id>")
def delete_event(event_id: int):
    try:
        plan_service.delete_event(event_id)
        return jsonify({"ok": True})
    except plan_service.PlanError as exc:
        return _error(exc)


@bp.get("/api/plan/settings")
def get_settings():
    return jsonify(plan_service.get_settings())


@bp.put("/api/plan/settings")
def update_settings():
    data = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(plan_service.update_settings(data))
    except plan_service.PlanError as exc:
        return _error(exc)


@bp.get("/api/plan/telegram/status")
def telegram_status():
    return jsonify(plan_telegram_jobs.status())


@bp.post("/api/plan/telegram/daily")
def telegram_daily():
    data = request.get_json(force=True, silent=True) or {}
    test = bool(data.get("test") or request.args.get("test") in ("1", "true", "yes"))
    try:
        return jsonify(plan_telegram_jobs.send_daily_list(test=test))
    except plan_service.PlanError as exc:
        return _error(exc)
