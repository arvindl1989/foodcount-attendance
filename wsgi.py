"""Production entry point, e.g. `gunicorn --preload wsgi:app`.

Set SEED_DEMO_DATA=1 to fill an empty database with the demo users and
entries on start-up. With --preload this runs once in the gunicorn master
before workers are forked.
"""
import os

from app import create_app
from seed import seed_if_empty

app = create_app()

if os.environ.get("SEED_DEMO_DATA") == "1" and seed_if_empty(app):
    print("Empty database: demo data created.", flush=True)
