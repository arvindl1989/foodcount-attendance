-- Schema is idempotent: it runs on every start and only creates what's missing.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id   TEXT    NOT NULL UNIQUE,          -- login username
    name          TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('employee', 'manager', 'admin')),
    manager_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    department    TEXT,
    location      TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_manager ON users(manager_id);

-- One row per user per working day they are NOT in the office.
-- No row means "in office".
CREATE TABLE IF NOT EXISTS attendance_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date       TEXT    NOT NULL,                     -- ISO date, YYYY-MM-DD
    status     TEXT    NOT NULL CHECK (status IN ('WFH', 'LEAVE')),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),   -- UTC
    updated_at TEXT    NOT NULL DEFAULT (datetime('now')),   -- UTC
    UNIQUE (user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance_entries(date);
