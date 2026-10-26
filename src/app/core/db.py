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
            # Another first connection may already be migrating; bootstrap must never lower its version.
            connection.executescript(SCHEMA.replace("PRAGMA user_version=3;", ""))
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
                if connection.execute("PRAGMA user_version").fetchone()[0] < 5:
                    connection.execute("PRAGMA user_version=5")
        if connection.execute("PRAGMA user_version").fetchone()[0] < 6:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                columns = {row["name"] for row in connection.execute("PRAGMA table_info(visit_requests)")}
                if "ended_at" not in columns:
                    connection.execute("ALTER TABLE visit_requests ADD COLUMN ended_at TEXT")
                connection.execute("""CREATE TABLE IF NOT EXISTS visit_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL REFERENCES visit_requests(id) ON DELETE CASCADE,
                    sender_role TEXT NOT NULL CHECK (sender_role IN ('patient','doctor')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )""")
                connection.execute("CREATE INDEX IF NOT EXISTS visit_messages_request_id ON visit_messages(request_id, id)")
                if connection.execute("PRAGMA user_version").fetchone()[0] < 6:
                    connection.execute("PRAGMA user_version=6")
        if connection.execute("PRAGMA user_version").fetchone()[0] < 7:
            # SQLite's table-rebuild procedure requires foreign_keys OFF outside a transaction.
            connection.execute("PRAGMA foreign_keys=OFF")
            try:
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    if connection.execute("PRAGMA user_version").fetchone()[0] < 7:
                        indexes = [row[0] for row in connection.execute(
                            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='users' AND sql IS NOT NULL"
                        )]
                        connection.execute("""CREATE TABLE users_new (
                            id TEXT PRIMARY KEY,
                            role TEXT NOT NULL CHECK (role IN ('patient','doctor','admin')),
                            username TEXT UNIQUE NOT NULL,
                            password_hash TEXT NOT NULL,
                            patient_id TEXT UNIQUE REFERENCES patients(id) ON DELETE CASCADE,
                            created_at TEXT NOT NULL,
                            CHECK ((role='patient' AND patient_id IS NOT NULL) OR
                                   (role IN ('doctor','admin') AND patient_id IS NULL))
                        )""")
                        connection.execute("INSERT INTO users_new SELECT * FROM users")
                        connection.execute("DROP TABLE users")
                        connection.execute("ALTER TABLE users_new RENAME TO users")
                        for sql in indexes:
                            connection.execute(sql)
                        columns = {row["name"] for row in connection.execute("PRAGMA table_info(doctors)")}
                        for name, kind in (("review_status", "TEXT NOT NULL DEFAULT 'pending'"), ("license_number", "TEXT"),
                                           ("reviewed_at", "TEXT"), ("review_note", "TEXT")):
                            if name not in columns:
                                connection.execute(f"ALTER TABLE doctors ADD COLUMN {name} {kind}")
                        connection.execute("UPDATE doctors SET review_status='approved' WHERE verified=1")
                        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS doctors_license_number ON doctors(license_number) WHERE license_number IS NOT NULL")
                        connection.execute("""CREATE TABLE IF NOT EXISTS admin_audit (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            admin_user_id TEXT NOT NULL,
                            action TEXT NOT NULL,
                            doctor_id TEXT NOT NULL,
                            from_status TEXT,
                            to_status TEXT,
                            note TEXT,
                            created_at TEXT NOT NULL
                        )""")
                        connection.execute("CREATE INDEX IF NOT EXISTS admin_audit_created ON admin_audit(created_at)")
                        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                            raise sqlite3.IntegrityError("Schema migration foreign key check failed")
                        connection.execute("PRAGMA user_version=7")
            finally:
                connection.execute("PRAGMA foreign_keys=ON")
        if connection.execute("PRAGMA user_version").fetchone()[0] < 8:
            from app.agent.intake import PROFILE_FIELDS
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute("PRAGMA user_version").fetchone()[0] < 8:
                    connection.execute("""CREATE TABLE IF NOT EXISTS patient_profiles (
                        patient_id TEXT PRIMARY KEY REFERENCES patients(id) ON DELETE CASCADE,
                        age INTEGER, height_cm REAL, weight_kg REAL, medical_history TEXT,
                        medications TEXT, medication_history TEXT, food_allergies TEXT, allergies TEXT,
                        medication_codes TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL
                    )""")
                    fields = ','.join(PROFILE_FIELDS)
                    complete = ' AND '.join(f'latest.{name} IS NOT NULL' for name in PROFILE_FIELDS)
                    connection.execute(f"""INSERT INTO patient_profiles(patient_id,{fields},medication_codes,updated_at)
                        SELECT s.patient_id,{','.join('s.' + name for name in PROFILE_FIELDS)},s.medication_codes,s.updated_at
                        FROM sessions s WHERE s.rowid=(SELECT latest.rowid FROM sessions latest
                            WHERE latest.patient_id=s.patient_id AND latest.done=1 AND latest.emergency=0 AND {complete}
                            ORDER BY latest.updated_at DESC,latest.created_at DESC,latest.rowid DESC LIMIT 1)
                        ON CONFLICT(patient_id) DO NOTHING""")
                    if "resubmitted_at" not in {row["name"] for row in connection.execute("PRAGMA table_info(doctors)")}:
                        connection.execute("ALTER TABLE doctors ADD COLUMN resubmitted_at TEXT")
                    connection.execute("PRAGMA user_version=8")
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
