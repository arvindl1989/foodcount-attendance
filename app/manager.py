"""Manager portal: month grid of direct reports."""
from datetime import timedelta

from flask import Blueprint, g, render_template, request

from . import attendance as att
from .auth import role_required
from .db import get_db

bp = Blueprint("manager", __name__, url_prefix="/manager")

FILTERS = {"ALL": "All", "WFH": "WFH only", "LEAVE": "Leave only"}


@bp.get("/")
@role_required("manager")
def team():
    today = att.today()
    first = att.parse_month(request.args.get("month"), default=today.replace(day=1))
    status_filter = request.args.get("status", "ALL").upper()
    if status_filter not in FILTERS:
        status_filter = "ALL"

    days = att.month_days(first)
    reports = get_db().execute(
        "SELECT * FROM users WHERE manager_id = ? ORDER BY name", (g.user["id"],)
    ).fetchall()
    ids = [r["id"] for r in reports]
    entries = att.entries_for_users(ids, days[0], days[-1] + timedelta(days=1))

    rows = []
    for person in reports:
        cells, wfh, leave = [], 0, 0
        for d in days:
            status = entries.get((person["id"], d.isoformat()))
            wfh += status == "WFH"
            leave += status == "LEAVE"
            shown = status if status_filter in ("ALL", status) else None
            cells.append({"status": shown, "weekend": att.is_weekend(d), "today": d == today})
        rows.append({"person": person, "cells": cells, "wfh": wfh, "leave": leave})

    # "Today" panel is always about today, whatever month is being viewed.
    todays = att.entries_for_users(ids, today, today + timedelta(days=1))
    today_status = {pid: s for (pid, _), s in todays.items()}
    away_today = {
        s: [p for p in reports if today_status.get(p["id"]) == s] for s in att.STATUSES
    }

    return render_template(
        "manager/team.html",
        rows=rows,
        days=days,
        month=first,
        prev_month=att.add_months(first, -1).strftime("%Y-%m"),
        next_month=att.add_months(first, 1).strftime("%Y-%m"),
        this_month=today.strftime("%Y-%m"),
        status_filter=status_filter,
        filters=FILTERS,
        today=today,
        away_today=away_today,
        team_size=len(reports),
    )
