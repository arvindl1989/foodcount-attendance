"""Attendance rules and queries shared by all portals.

Keeping this free of request handling means the rules (what can be edited,
how the food count is computed) live in one place and are easy to test.
"""
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import current_app

from .db import get_db

STATUSES = ("WFH", "LEAVE")
STATUS_LABELS = {"WFH": "Work from home", "LEAVE": "Leave", None: "In office"}


# --- Time ---------------------------------------------------------------

def now():
    tz = current_app.config.get("APP_TIMEZONE")
    return datetime.now(ZoneInfo(tz)) if tz else datetime.now()


def today():
    return now().date()


def cutoff_time():
    cfg = current_app.config
    return time(cfg["CUTOFF_HOUR"], cfg["CUTOFF_MINUTE"])


def cutoff_label():
    return cutoff_time().strftime("%H:%M")


def cutoff_passed(at=None):
    at = at or now()
    return at.time() >= cutoff_time()


def is_weekend(day):
    return day.weekday() >= 5


def edit_block_reason(day, at=None):
    """Why `day` can't be edited right now, or None if it can."""
    at = at or now()
    if is_weekend(day):
        return "Weekends can't be edited."
    if day < at.date():
        return "Past dates can't be edited."
    if day == at.date() and cutoff_passed(at):
        return f"Today's status is locked after the {cutoff_label()} cutoff."
    return None


# --- Date parsing helpers -----------------------------------------------

def parse_iso_date(value, default=None):
    try:
        return date.fromisoformat((value or "")[:10])
    except ValueError:
        return default


def parse_month(value, default=None):
    """'2026-10' -> date(2026, 10, 1). Falls back to `default` or this month."""
    try:
        year, month = (int(p) for p in (value or "").split("-"))
        return date(year, month, 1)
    except ValueError:
        return default or today().replace(day=1)


def add_months(first_of_month, n):
    idx = first_of_month.year * 12 + first_of_month.month - 1 + n
    return date(idx // 12, idx % 12 + 1, 1)


def month_days(first_of_month):
    count = monthrange(first_of_month.year, first_of_month.month)[1]
    return [first_of_month + timedelta(days=i) for i in range(count)]


# --- Queries -------------------------------------------------------------

def entries_for_users(user_ids, start, end):
    """Entries in [start, end) as {(user_id, 'YYYY-MM-DD'): status}."""
    if not user_ids:
        return {}
    placeholders = ",".join("?" * len(user_ids))
    rows = get_db().execute(
        f"""SELECT user_id, date, status FROM attendance_entries
            WHERE user_id IN ({placeholders}) AND date >= ? AND date < ?""",
        (*user_ids, start.isoformat(), end.isoformat()),
    ).fetchall()
    return {(r["user_id"], r["date"]): r["status"] for r in rows}


def set_status(user_id, day, status):
    """Set a user's status for a day. status=None clears it (back to office)."""
    db = get_db()
    if status is None:
        db.execute(
            "DELETE FROM attendance_entries WHERE user_id = ? AND date = ?",
            (user_id, day.isoformat()),
        )
    else:
        if status not in STATUSES:
            raise ValueError(f"Unknown status: {status}")
        db.execute(
            """INSERT INTO attendance_entries (user_id, date, status)
               VALUES (?, ?, ?)
               ON CONFLICT (user_id, date) DO UPDATE
               SET status = excluded.status, updated_at = datetime('now')""",
            (user_id, day.isoformat(), status),
        )
    db.commit()


def day_roster(day):
    """Every person in the headcount with their status (None = in office) for `day`."""
    roles = current_app.config["HEADCOUNT_ROLES"]
    placeholders = ",".join("?" * len(roles))
    return get_db().execute(
        f"""SELECT u.id, u.employee_id, u.name, u.role, u.department, u.location,
                   a.status
            FROM users u
            LEFT JOIN attendance_entries a ON a.user_id = u.id AND a.date = ?
            WHERE u.role IN ({placeholders})
            ORDER BY u.employee_id""",
        (day.isoformat(), *roles),
    ).fetchall()


def _blank_counts():
    return {"total": 0, "wfh": 0, "leave": 0, "in_office": 0}


def _tally(counts, status, closed):
    counts["total"] += 1
    if status == "WFH":
        counts["wfh"] += 1
    elif status == "LEAVE":
        counts["leave"] += 1
    elif not closed:
        counts["in_office"] += 1


def headcount(day):
    """Food count for one day, overall and broken down by location/department.

    in_office = total - WFH - leave. On weekends the office is closed, so
    in_office is 0.
    """
    closed = is_weekend(day)
    overall = _blank_counts()
    by_location, by_department = {}, {}
    for row in day_roster(day):
        _tally(overall, row["status"], closed)
        _tally(by_location.setdefault(row["location"] or "—", _blank_counts()), row["status"], closed)
        _tally(by_department.setdefault(row["department"] or "—", _blank_counts()), row["status"], closed)
    return {
        "date": day,
        "closed": closed,
        **overall,
        "by_location": sorted(by_location.items()),
        "by_department": sorted(by_department.items()),
    }


def forecast(start, days):
    """Headcount for `days` consecutive days starting at `start`."""
    result = []
    for i in range(days):
        hc = headcount(start + timedelta(days=i))
        del hc["by_location"], hc["by_department"]
        result.append(hc)
    return result
