import sqlite3
from datetime import UTC, datetime

from app.core.config import Settings

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
CREATE TABLE IF NOT EXISTS triage_results (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    specialty_code TEXT NOT NULL,
    urgency TEXT NOT NULL,
    source TEXT NOT NULL,
    reason_fa TEXT,
    doctor_summary_fa TEXT NOT NULL,
    considerations_fa TEXT NOT NULL,
    model TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('patient','doctor')),
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    patient_id TEXT UNIQUE REFERENCES patients(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    CHECK ((role='patient' AND patient_id IS NOT NULL) OR (role='doctor' AND patient_id IS NULL))
);
CREATE TABLE IF NOT EXISTS doctors (
    id TEXT PRIMARY KEY,
    user_id TEXT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    name_fa TEXT NOT NULL,
    specialty_code TEXT NOT NULL,
    expertise TEXT NOT NULL,
    score REAL,
    verified INTEGER NOT NULL CHECK (verified IN (0,1)),
    available INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0,1)),
    last_seen_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS visit_requests (
    id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    specialty_code TEXT NOT NULL,
    doctor_id TEXT REFERENCES doctors(id),
    status TEXT NOT NULL CHECK (status IN ('pending','accepted','cancelled','expired')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    accepted_at TEXT,
    CHECK ((status='accepted' AND doctor_id IS NOT NULL) OR (status<>'accepted' AND doctor_id IS NULL))
);
CREATE INDEX IF NOT EXISTS requests_specialty_status_created ON visit_requests(specialty_code, status, created_at);
CREATE INDEX IF NOT EXISTS requests_doctor_status ON visit_requests(doctor_id, status);
CREATE INDEX IF NOT EXISTS requests_patient_created ON visit_requests(patient_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS requests_active_session ON visit_requests(session_id) WHERE status IN ('pending','accepted');
CREATE INDEX IF NOT EXISTS auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS doctors_specialty ON doctors(specialty_code, verified);
PRAGMA user_version=3;
"""


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(Settings().db_path, timeout=10)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA secure_delete=ON")
        if connection.execute("PRAGMA user_version").fetchone()[0] < 3:
            connection.executescript(SCHEMA)
        if connection.execute("PRAGMA user_version").fetchone()[0] < 5:
            # ponytail: explicit additive SQLite migrations; use versioned migration files/tooling when migrations grow.
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                columns = {row["name"] for row in connection.execute("PRAGMA table_info(sessions)")}
                for name, kind in (("height_cm", "REAL"), ("weight_kg", "REAL"), ("chief_complaint", "TEXT"),
                                   ("medical_history", "TEXT"), ("medication_history", "TEXT"), ("food_allergies", "TEXT"),
                                   ("additional_context", "TEXT")):
                    if name not in columns:
                        connection.execute(f"ALTER TABLE sessions ADD COLUMN {name} {kind}")
                connection.execute("PRAGMA user_version=5")
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
