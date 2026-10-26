"""SQLite connection handling."""
import sqlite3
from importlib import resources

from flask import current_app, g


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """Return the request-scoped connection, opening it on first use."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(conn):
    schema = resources.files(__package__).joinpath("schema.sql").read_text()
    conn.executescript(schema)
    conn.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    # Create the database file and tables on first run.
    conn = connect(app.config["DATABASE"])
    try:
        init_db(conn)
    finally:
        conn.close()
