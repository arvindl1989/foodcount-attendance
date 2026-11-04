"""Production entry point, e.g. `gunicorn --preload wsgi:app`.

On every start the users are synced from the roster file (data/roster.csv).
Set SEED_DEMO_DATA=1 (or true/yes) to also add random sample WFH / leave
entries when there are none. With --preload this runs once in the gunicorn
master before workers are forked.
"""
import os

from app import create_app
from seed import setup_data

app = create_app()

sample = os.environ.get("SEED_DEMO_DATA", "").strip().lower() in ("1", "true", "yes", "on")
setup_data(app, sample_entries=sample, log=lambda msg: print(msg, flush=True))
