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
# ponytail: a fixed 90-second window tolerates throttled hidden-tab heartbeats every 20 seconds; use shared/push presence when scaling.
ONLINE_SECONDS = 90
ONLINE_SQL = "CASE WHEN verified=1 AND available=1 AND last_seen_at>=:cutoff AND last_seen_at<=:now THEN 1 ELSE 0 END"


def specialty(code: str) -> dict:
    entry = next(item for item in load_doctors()["specialties"] if item["code"] == code)
    return {"code": entry["code"], "name_fa": entry["name_fa"]}


def seed_doctors() -> None:
    settings = Settings()
    with closing(db.connect()) as connection, connection:
        for doctor in load_doctors()["doctors"]:
            connection.execute(
                """INSERT INTO doctors(id, name_fa, specialty_code, expertise, score, verified, created_at, review_status)
                   VALUES (:id, :name_fa, :specialty_code, :expertise, :score, 1, :created_at, 'approved')
                   ON CONFLICT(id) DO UPDATE SET
                     name_fa=CASE WHEN doctors.user_id IS NULL THEN excluded.name_fa ELSE doctors.name_fa END,
                     specialty_code=CASE WHEN doctors.user_id IS NULL THEN excluded.specialty_code ELSE doctors.specialty_code END,
                     expertise=CASE WHEN doctors.user_id IS NULL THEN excluded.expertise ELSE doctors.expertise END,
                     score=excluded.score, last_seen_at=NULL""",
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
        connection.execute("BEGIN IMMEDIATE")
        require_doctor(connection, doctor_id)
        connection.execute("UPDATE doctors SET available=? WHERE id=?", (available, doctor_id))
    return {"available": available}


def _profile(row) -> dict:
    return {"name_fa": row["name_fa"], "specialty": specialty(row["specialty_code"]),
            "expertise": json.loads(row["expertise"]), "license_number": row["license_number"],
            "score": row["score"], "status": row["review_status"], "review_note": row["review_note"],
            "resubmitted_at": row["resubmitted_at"]}


def profile(doctor_id: str) -> dict:
    with closing(db.connect()) as connection:
        return _profile(connection.execute("SELECT * FROM doctors WHERE id=?", (doctor_id,)).fetchone())


def update_profile(doctor_id: str, changes: dict) -> dict:
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM doctors WHERE id=?", (doctor_id,)).fetchone()
        if row["review_status"] == "suspended":
            raise ServiceError(403, "profile_locked", "Profile is locked while the doctor is suspended")
        values = {name: row[name] for name in ("name_fa", "specialty_code", "expertise", "license_number")}
        values.update({**changes, **({"expertise": json.dumps(changes["expertise"], ensure_ascii=False)} if "expertise" in changes else {})})
        if connection.execute("SELECT 1 FROM doctors WHERE license_number=? AND id<>?", (values["license_number"], doctor_id)).fetchone():
            raise ServiceError(409, "license_unavailable", "License number unavailable")
        changed = any(values[name] != row[name] for name in values)
        identity_changed = any(values[name] != row[name] for name in ("specialty_code", "license_number"))
        target = row["review_status"]
        resubmit = changed and target == "rejected" or target == "approved" and identity_changed and not Settings().doctor_auto_verify
        if resubmit:
            if target == "approved" and connection.execute("SELECT 1 FROM visit_requests WHERE doctor_id=? AND status='accepted' AND ended_at IS NULL", (doctor_id,)).fetchone():
                raise ServiceError(409, "active_visits", "Doctor has active visits")
            target = "approved" if Settings().doctor_auto_verify else "pending"
        # Keep the redundant verification column in sync with the review state, as in admin.review.
        connection.execute("""UPDATE doctors SET name_fa=:name_fa,specialty_code=:specialty_code,
            expertise=:expertise,license_number=:license_number,review_status=:status,verified=:verified,
            available=CASE WHEN :offline THEN 0 ELSE available END,
            last_seen_at=CASE WHEN :offline THEN NULL ELSE last_seen_at END,
            review_note=CASE WHEN :resubmit THEN NULL ELSE review_note END,
            resubmitted_at=CASE WHEN :resubmit THEN :now ELSE resubmitted_at END WHERE id=:id""",
            {**values, "status": target, "verified": target == "approved", "offline": resubmit and target == "pending",
             "resubmit": resubmit, "now": db.utc_now(), "id": doctor_id})
        return _profile(connection.execute("SELECT * FROM doctors WHERE id=?", (doctor_id,)).fetchone())
