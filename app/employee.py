"""Employee portal: personal WFH / leave calendar."""
from flask import Blueprint, g, jsonify, render_template, request

from . import attendance as att
from .auth import role_required
from .db import get_db

bp = Blueprint("employee", __name__, url_prefix="/employee")


@bp.get("/")
@role_required("employee")
def calendar():
    at = att.now()
    return render_template(
        "employee/calendar.html",
        today=at.date().isoformat(),
        cutoff_label=att.cutoff_label(),
        cutoff_passed=att.cutoff_passed(at),
    )


@bp.get("/api/entries")
@role_required("employee", api=True)
def list_entries():
    """The user's own entries in [start, end). FullCalendar sends both."""
    start = att.parse_iso_date(request.args.get("start"))
    end = att.parse_iso_date(request.args.get("end"))
    if start is None or end is None or end <= start:
        return jsonify(error="start and end must be ISO dates with start < end."), 400
    if (end - start).days > 120:
        return jsonify(error="Date range too large."), 400

    rows = get_db().execute(
        """SELECT date, status FROM attendance_entries
           WHERE user_id = ? AND date >= ? AND date < ? ORDER BY date""",
        (g.user["id"], start.isoformat(), end.isoformat()),
    ).fetchall()
    return jsonify([{"date": r["date"], "status": r["status"]} for r in rows])


@bp.post("/api/entries")
@role_required("employee", api=True)
def set_entry():
    """Body: {"date": "YYYY-MM-DD", "status": "WFH" | "LEAVE" | "CLEAR"}"""
    data = request.get_json(silent=True) or {}
    day = att.parse_iso_date(data.get("date"))
    status = data.get("status")
    if day is None:
        return jsonify(error="A valid date is required."), 400
    if status == "CLEAR":
        status = None
    elif status not in att.STATUSES:
        return jsonify(error="Status must be WFH, LEAVE or CLEAR."), 400

    reason = att.edit_block_reason(day)
    if reason:
        return jsonify(error=reason), 422

    att.set_status(g.user["id"], day, status)
    return jsonify(date=day.isoformat(), status=status)
