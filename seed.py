"""Populate the database with demo users and random WFH / leave entries.

Usage:
    python seed.py            # seed only if there are no users yet
    python seed.py --reset    # delete ALL users and entries, then seed again

`python run.py` calls seed_if_empty() automatically, so you only need this
script to reset the demo data.
"""
import argparse
import random
from datetime import timedelta

from werkzeug.security import generate_password_hash

from app import create_app
from app.attendance import add_months, is_weekend, month_days, today
from app.db import get_db

DEPARTMENTS = ["Engineering", "Finance", "Operations"]
LOCATIONS = ["Head Office", "City Centre"]

ADMIN = ("ADMIN01", "Alex Morgan", "admin123")
MANAGERS = [  # employee_id, name, department
    ("MGR01", "Priya Raman", "Engineering"),
    ("MGR02", "David Okafor", "Finance"),
    ("MGR03", "Sofia Martinez", "Operations"),
]
MANAGER_PASSWORD = "manager123"
EMPLOYEE_PASSWORD = "emp123"
EMPLOYEE_NAMES = [
    "Aarav Shah", "Bella Thompson", "Carlos Silva", "Diana Chen", "Ethan Brooks",
    "Fatima Khan", "George Miller", "Hana Suzuki", "Ivan Petrov", "Julia Rossi",
    "Kofi Mensah", "Lena Fischer", "Mohammed Ali", "Nina Kowalski", "Oscar Lindqvist",
    "Pooja Nair", "Quentin Dubois", "Rachel Green", "Samuel Adeyemi", "Tara O'Neill",
    "Umar Farooq", "Valentina Cruz", "William Park", "Xin Li", "Yusuf Demir",
    "Zara Ahmed", "Arjun Mehta", "Chloe Martin", "Daniel Kim", "Emma Wilson",
]


def seed(db, rng=None, reference_day=None):
    """Insert demo users and entries for this month and next. Returns user count."""
    rng = rng or random.Random()
    reference_day = reference_day or today()

    def add_user(employee_id, name, password, role, manager_id=None, department=None, location=None):
        cur = db.execute(
            """INSERT INTO users (employee_id, name, password_hash, role, manager_id, department, location)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (employee_id, name, generate_password_hash(password), role, manager_id, department, location),
        )
        return cur.lastrowid

    add_user(ADMIN[0], ADMIN[1], ADMIN[2], "admin", department="Operations", location=LOCATIONS[0])

    manager_ids = []
    for i, (emp_id, name, dept) in enumerate(MANAGERS):
        manager_ids.append(add_user(emp_id, name, MANAGER_PASSWORD, "manager",
                                    department=dept, location=LOCATIONS[i % 2]))

    employee_ids = []
    for i, name in enumerate(EMPLOYEE_NAMES):
        team = i % len(MANAGERS)
        employee_ids.append(add_user(
            f"EMP{i + 1:03d}", name, EMPLOYEE_PASSWORD, "employee",
            manager_id=manager_ids[team],
            department=MANAGERS[team][2],
            location=LOCATIONS[(i // len(MANAGERS)) % 2],
        ))

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
        for user_id in rng.sample(employee_ids, 3):
            if len(on_leave) >= 2:
                break
            rows = [r for r in rows if not (r[0] == user_id and r[1] == day)]
            rows.append((user_id, day, "LEAVE"))
            on_leave.add(user_id)

    db.executemany("INSERT INTO attendance_entries (user_id, date, status) VALUES (?, ?, ?)", rows)
    db.commit()
    return 1 + len(manager_ids) + len(employee_ids)


def reset(db):
    db.execute("DELETE FROM attendance_entries")
    db.execute("DELETE FROM users")
    db.commit()


def seed_if_empty(app):
    with app.app_context():
        db = get_db()
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return False
        seed(db)
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete all existing data first")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        db = get_db()
        if args.reset:
            reset(db)
        elif db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            print("Database already has users; nothing to do. Use --reset to start over.")
            return
        count = seed(db)
        entries = db.execute("SELECT COUNT(*) FROM attendance_entries").fetchone()[0]
        print(f"Seeded {count} users and {entries} attendance entries into {app.config['DATABASE']}")


if __name__ == "__main__":
    main()
