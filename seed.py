"""Load users from the roster file, and optionally sample WFH / leave entries.

The roster (data/roster.csv, or ROSTER_FILE) is the list of everyone who can
log in. Syncing it:
  - adds people who are new, with the initial password (INITIAL_PASSWORD)
  - updates name, role, manager, department and location of existing people
    (passwords they have changed are kept)
  - removes people who are no longer in the file, with their entries

Usage:
    python seed.py                    # sync users from the roster
    python seed.py --sample-entries   # ...and add random entries if there are none
    python seed.py --reset --sample-entries   # wipe everything, start over

`python run.py` syncs the roster and adds sample entries to an empty
database automatically. On a server, wsgi.py syncs the roster on every start.
"""
import argparse
import csv
import os
import random
from datetime import timedelta

from flask import current_app
from werkzeug.security import generate_password_hash

from app import create_app
from app.attendance import add_months, is_weekend, month_days, today
from app.db import get_db

ROLES = ("employee", "manager", "admin")


class RosterError(ValueError):
    pass


def _clean(value):
    return " ".join((value or "").split())


def read_roster(path):
    """Parse and validate the roster CSV. Returns a list of dicts."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    people, seen = [], set()
    for line, raw in enumerate(rows, start=2):
        p = {k: _clean(raw.get(k)) for k in ("employee_id", "name", "role", "manager", "department", "location")}
        p["employee_id"] = p["employee_id"].upper()
        p["role"] = p["role"].lower()
        p["bus_pass"] = _clean(raw.get("bus_pass")).lower() in ("yes", "y", "1", "true")
        if not p["employee_id"] and not p["name"]:
            continue  # blank line
        if not p["employee_id"] or not p["name"]:
            raise RosterError(f"{path} line {line}: employee_id and name are required")
        if p["role"] not in ROLES:
            raise RosterError(f"{path} line {line}: role must be one of {', '.join(ROLES)}")
        if p["employee_id"] in seen:
            raise RosterError(f"{path} line {line}: duplicate employee_id {p['employee_id']}")
        seen.add(p["employee_id"])
        people.append(p)

    # The manager column holds the manager's name, as in the team lists.
    by_name = {}
    for p in people:
        by_name.setdefault(p["name"].casefold(), []).append(p)
    for p in people:
        if not p["manager"]:
            continue
        matches = by_name.get(p["manager"].casefold(), [])
        if len(matches) != 1:
            problem = "no one in the roster" if not matches else "more than one person in the roster"
            raise RosterError(f"{p['name']}'s manager '{p['manager']}' matches {problem}")
        p["manager_employee_id"] = matches[0]["employee_id"]
    return people


def sync_roster(db, people):
    """Make the users table match `people`. Returns (added, updated, removed)."""
    existing = {r["employee_id"]: r for r in db.execute("SELECT id, employee_id FROM users")}
    added = updated = 0
    for p in people:
        values = (p["name"], p["role"], p["department"] or None, p["location"] or None, int(p["bus_pass"]))
        if p["employee_id"] in existing:
            db.execute("""UPDATE users SET name = ?, role = ?, department = ?, location = ?, bus_pass = ?
                          WHERE employee_id = ?""", (*values, p["employee_id"]))
            updated += 1
        else:
            db.execute(
                """INSERT INTO users (employee_id, name, role, department, location, bus_pass, password_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (p["employee_id"], *values, generate_password_hash(current_app.config["INITIAL_PASSWORD"])),
            )
            added += 1

    ids = {r["employee_id"]: r["id"] for r in db.execute("SELECT id, employee_id FROM users")}
    for p in people:
        manager = p.get("manager_employee_id")
        db.execute("UPDATE users SET manager_id = ? WHERE employee_id = ?",
                   (ids[manager] if manager else None, p["employee_id"]))

    keep = {p["employee_id"] for p in people}
    gone = [eid for eid in ids if eid not in keep]
    for eid in gone:
        db.execute("DELETE FROM users WHERE employee_id = ?", (eid,))  # entries cascade
    db.commit()
    return added, updated, len(gone)


def add_sample_entries(db, rng=None, reference_day=None):
    """Random WFH / leave for this month and next, for every employee."""
    rng = rng or random.Random()
    reference_day = reference_day or today()
    employee_ids = [r["id"] for r in db.execute("SELECT id FROM users WHERE role = 'employee' ORDER BY id")]
    if not employee_ids:
        return 0

    first = reference_day.replace(day=1)
    workdays = [d for d in month_days(first) + month_days(add_months(first, 1)) if not is_weekend(d)]

    rows = []
    for user_id in employee_ids:
        status_by_day = {}
        wfh_rate = rng.uniform(0.1, 0.4)
        for d in workdays:
            if rng.random() < wfh_rate:
                status_by_day[d] = "WFH"
        # A couple of short leave blocks across the two months.
        for _ in range(rng.randint(1, 4)):
            start = rng.choice(workdays)
            for offset in range(rng.randint(1, 3)):
                d = start + timedelta(days=offset)
                if not is_weekend(d) and d in workdays:
                    status_by_day[d] = "LEAVE"
        rows += [(user_id, d.isoformat(), s) for d, s in status_by_day.items()]

    # Make sure the "on leave today" panels have someone in them for the demo.
    if not is_weekend(reference_day):
        day = reference_day.isoformat()
        on_leave = {r[0] for r in rows if r[1] == day and r[2] == "LEAVE"}
        for user_id in rng.sample(employee_ids, min(3, len(employee_ids))):
            if len(on_leave) >= 2:
                break
            rows = [r for r in rows if not (r[0] == user_id and r[1] == day)]
            rows.append((user_id, day, "LEAVE"))
            on_leave.add(user_id)

    db.executemany("INSERT INTO attendance_entries (user_id, date, status) VALUES (?, ?, ?)", rows)
    db.commit()
    return len(rows)


def reset(db):
    db.execute("DELETE FROM attendance_entries")
    db.execute("DELETE FROM users")
    db.commit()


def setup_data(app, sample_entries=False, log=print):
    """Sync the roster; add sample entries if asked and there are none yet."""
    with app.app_context():
        db = get_db()
        added, updated, removed = sync_roster(db, read_roster(app.config["ROSTER_FILE"]))
        log(f"Roster: {added} added, {updated} updated, {removed} removed.")
        if sample_entries and not db.execute("SELECT 1 FROM attendance_entries LIMIT 1").fetchone():
            log(f"Sample data: {add_sample_entries(db)} WFH / leave entries added.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete all users and entries first")
    parser.add_argument("--sample-entries", action="store_true",
                        help="add random WFH / leave entries if there are none")
    args = parser.parse_args()

    app = create_app()
    if args.reset:
        with app.app_context():
            reset(get_db())
    setup_data(app, sample_entries=args.sample_entries)


if __name__ == "__main__":
    main()
