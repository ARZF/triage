import sqlite3
from datetime import UTC, datetime

from app.config import Settings

# ponytail: stdlib sqlite3, single file, no migrations framework; upgrade to Postgres with SQLAlchemy/Alembic when needed.
# JSON-text code arrays become join tables when querying by code is needed.
SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    step TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    emergency INTEGER NOT NULL DEFAULT 0,
    returning_profile INTEGER NOT NULL DEFAULT 0,
    age INTEGER,
    symptoms TEXT,
    duration TEXT,
    severity INTEGER,
    medications TEXT,
    allergies TEXT,
    symptom_codes TEXT NOT NULL DEFAULT '[]',
    medication_codes TEXT NOT NULL DEFAULT '[]',
    reply TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'bot')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_patient_created ON sessions(patient_id, created_at);
CREATE INDEX IF NOT EXISTS messages_session_id ON messages(session_id, id);
PRAGMA user_version=1;
"""


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(Settings().db_path, timeout=10)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(SCHEMA)
        return connection
    except BaseException:
        connection.close()
        raise


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def add_message(connection: sqlite3.Connection, session_id: str, role: str, content: str, timestamp: str) -> None:
    connection.execute(
        "INSERT INTO messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, role, content, timestamp),
    )
