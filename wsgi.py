"""Production entry point, e.g. `gunicorn --preload wsgi:app`.

Set SEED_DEMO_DATA=1 (or true/yes) to fill an empty database with the demo
users and entries on start-up. With --preload this runs once in the gunicorn
master before workers are forked.
"""
import os

from app import create_app
from app.db import connect
from seed import seed_if_empty

app = create_app()

seed_flag = os.environ.get("SEED_DEMO_DATA", "").strip().lower()
if seed_flag in ("1", "true", "yes", "on") and seed_if_empty(app):
    print("Empty database: demo data created.", flush=True)

_conn = connect(app.config["DATABASE"])
_users = _conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
_conn.close()
print(f"Database {app.config['DATABASE']}: {_users} users.", flush=True)
if _users == 0:
    print("WARNING: no user accounts, so nobody can log in. "
          "Set SEED_DEMO_DATA=1 to load the demo accounts.", flush=True)
