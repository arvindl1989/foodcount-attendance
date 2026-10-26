"""Application settings.

Every value can be overridden with an environment variable of the same name,
so the defaults here are what you get with a plain `python run.py`.
"""
import os
from datetime import timedelta


class Config:
    # Signing key for session cookies. When unset, a random key is generated
    # once and stored in instance/secret_key so sessions survive restarts.
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # Path to the SQLite file. When unset: instance/foodcount.sqlite3
    DATABASE = os.environ.get("DATABASE")

    # Employees can't change *today's* status at or after this time.
    CUTOFF_HOUR = int(os.environ.get("CUTOFF_HOUR", 10))
    CUTOFF_MINUTE = int(os.environ.get("CUTOFF_MINUTE", 0))

    # IANA time zone used for "today" and the cutoff, e.g. "Asia/Kolkata".
    # Empty means the server's local time.
    APP_TIMEZONE = os.environ.get("APP_TIMEZONE") or None

    # Number of days shown in the admin's forward view.
    FORECAST_DAYS = 7

    # Which roles count towards the company headcount / food count.
    HEADCOUNT_ROLES = ("employee", "manager", "admin")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
