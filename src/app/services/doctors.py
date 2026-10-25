import json
import logging
from contextlib import closing
from datetime import datetime, timedelta
from uuid import uuid4

from app.agent.doctors import load_doctors
from app.core import db, security
from app.core.config import Settings
from app.core.errors import ServiceError

logger = logging.getLogger(__name__)
# ponytail: single process and SQLite, polling-based presence; use shared presence tracking when scaling.
# ponytail: a fixed 45-second heartbeat window suits 10-second polling; make presence configurable or push-based when needed.
ONLINE_SECONDS = 45
ONLINE_SQL = "CASE WHEN verified=1 AND available=1 AND last_seen_at>=:cutoff AND last_seen_at<=:now THEN 1 ELSE 0 END"


def specialty(code: str) -> dict:
    entry = next(item for item in load_doctors()["specialties"] if item["code"] == code)
    return {"code": entry["code"], "name_fa": entry["name_fa"]}


def seed_doctors() -> None:
    settings = Settings()
    with closing(db.connect()) as connection, connection:
        for doctor in load_doctors()["doctors"]:
            connection.execute(
                """INSERT INTO doctors(id, name_fa, specialty_code, expertise, score, verified, created_at)
                   VALUES (:id, :name_fa, :specialty_code, :expertise, :score, 1, :created_at)
                   ON CONFLICT(id) DO UPDATE SET name_fa=excluded.name_fa,
                     specialty_code=excluded.specialty_code, expertise=excluded.expertise,
                     score=excluded.score, verified=1, last_seen_at=NULL""",
                {**doctor, "expertise": json.dumps(doctor["expertise"], ensure_ascii=False), "created_at": db.utc_now()},
            )
            if settings.demo_doctor_password:
                row = connection.execute("SELECT id FROM users WHERE username=?", (doctor["id"],)).fetchone()
                user_id = row["id"] if row else uuid4().hex
                password_hash = security.hash_password(settings.demo_doctor_password)
                connection.execute(
                    """INSERT INTO users(id, role, username, password_hash, created_at)
                       VALUES (?, 'doctor', ?, ?, ?) ON CONFLICT(username)
                       DO UPDATE SET password_hash=excluded.password_hash""",
                    (user_id, doctor["id"], password_hash, db.utc_now()),
                )
                connection.execute("UPDATE doctors SET user_id=? WHERE id=?", (user_id, doctor["id"]))
    if not settings.demo_doctor_password:
        logger.info("seed_doctor_logins_disabled")


def public_doctor(row) -> dict:
    return {key: (json.loads(row[key]) if key == "expertise" else row[key])
            for key in ("id", "name_fa", "expertise", "score")}


def query_specialty(connection, code: str, online_only: bool = False) -> list[dict]:
    now = db.utc_now()
    cutoff = (datetime.fromisoformat(now) - timedelta(seconds=ONLINE_SECONDS)).isoformat(timespec="microseconds")
    query = f"""SELECT *, {ONLINE_SQL} AS online FROM doctors
                WHERE specialty_code=:code AND verified=1"""
    if online_only:
        query += f" AND ({ONLINE_SQL})=1"
    query += " ORDER BY online DESC, score IS NULL, score DESC, name_fa, id LIMIT 10"
    rows = connection.execute(query, {"code": code, "now": now, "cutoff": cutoff}).fetchall()
    return [{**public_doctor(row), "online": bool(row["online"])} for row in rows]


def for_specialty(code: str) -> list[dict]:
    with closing(db.connect()) as connection:
        return query_specialty(connection, code)


def require_doctor(connection, doctor_id: str):
    doctor = connection.execute("SELECT * FROM doctors WHERE id=? AND verified=1", (doctor_id,)).fetchone()
    if doctor is None:
        raise ServiceError(403, "doctor_unverified", "Doctor is not verified")
    return doctor


def set_available(doctor_id: str, available: bool) -> dict:
    with closing(db.connect()) as connection, connection:
        require_doctor(connection, doctor_id)
        connection.execute("UPDATE doctors SET available=? WHERE id=?", (available, doctor_id))
    return {"available": available}
