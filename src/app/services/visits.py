import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from uuid import uuid4

from app.agent.context import build_context
from app.core import db
from app.core.config import Settings
from app.core.errors import ServiceError
from app.services import doctors

AI_NOTICE = "این متن توسط هوش مصنوعی تولید شده، تأیید نشده و تشخیص پزشکی نیست؛ فقط برای بررسی پزشک است."


def _cutoff(now: str) -> str:
    return (datetime.fromisoformat(now) - timedelta(minutes=Settings().request_ttl_minutes)).isoformat(timespec="microseconds")


def expire_requests() -> None:
    now = db.utc_now()
    with closing(db.connect()) as connection, connection:
        connection.execute(
            "UPDATE visit_requests SET status='expired', updated_at=? WHERE status='pending' AND created_at<?",
            (now, _cutoff(now)),
        )


def request_status(row, cutoff: str) -> str:
    return "expired" if row["status"] == "pending" and row["created_at"] < cutoff else row["status"]


def _patient_item(connection, row, cutoff: str | None = None) -> dict:
    doctor = connection.execute("SELECT * FROM doctors WHERE id=?", (row["doctor_id"],)).fetchone() if row["doctor_id"] else None
    return {
        "id": row["id"], "status": request_status(row, cutoff or _cutoff(db.utc_now())), "created_at": row["created_at"],
        "session_id": row["session_id"], "accepted_at": row["accepted_at"], "ended_at": row["ended_at"],
        "specialty": doctors.specialty(row["specialty_code"]),
        "doctor": doctors.public_doctor(doctor) if doctor else None,
        "ended": row["ended_at"] is not None,
    }


def create(patient_id: str, session_id: str) -> dict:
    expire_requests()
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        session = connection.execute(
            "SELECT * FROM sessions WHERE id=? AND patient_id=?", (session_id, patient_id)
        ).fetchone()
        if session is None:
            raise ServiceError(404, "http_404", "Not Found")
        if not session["done"] or session["emergency"]:
            raise ServiceError(409, "intake_not_ready", "Intake must be complete and non-emergency")
        triage = connection.execute("SELECT * FROM triage_results WHERE session_id=?", (session_id,)).fetchone()
        if triage is None:
            raise ServiceError(409, "triage_required", "Triage result required")
        if triage["urgency"] == "emergency":
            raise ServiceError(409, "emergency_triage", "Emergency triage cannot request a visit")
        if not doctors.query_specialty(connection, triage["specialty_code"], online_only=True):
            raise ServiceError(409, "no_online_doctor", "No online doctor for this specialty")
        now = db.utc_now()
        request_id = uuid4().hex
        try:
            connection.execute(
                """INSERT INTO visit_requests(id, patient_id, session_id, specialty_code, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
                (request_id, patient_id, session_id, triage["specialty_code"], now, now),
            )
        except sqlite3.IntegrityError:
            raise ServiceError(409, "active_request_exists", "An active request already exists") from None
        row = connection.execute("SELECT * FROM visit_requests WHERE id=?", (request_id,)).fetchone()
        return _patient_item(connection, row)


def patient_requests(patient_id: str) -> list[dict]:
    cutoff = _cutoff(db.utc_now())
    with closing(db.connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM visit_requests WHERE patient_id=? ORDER BY created_at DESC, rowid DESC", (patient_id,)
        ).fetchall()
        return [_patient_item(connection, row, cutoff) for row in rows]


def cancel(patient_id: str, request_id: str) -> dict:
    expire_requests()
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM visit_requests WHERE id=? AND patient_id=?", (request_id, patient_id)
        ).fetchone()
        if row is None:
            raise ServiceError(404, "http_404", "Not Found")
        if row["status"] != "pending":
            raise ServiceError(409, "request_not_pending", "Request is no longer pending")
        connection.execute("UPDATE visit_requests SET status='cancelled', updated_at=? WHERE id=?", (db.utc_now(), request_id))
        return _patient_item(connection, connection.execute("SELECT * FROM visit_requests WHERE id=?", (request_id,)).fetchone())


def _doctor_item(connection, row, doctor_id: str) -> dict:
    session = connection.execute("SELECT * FROM sessions WHERE id=?", (row["session_id"],)).fetchone()
    triage = connection.execute("SELECT * FROM triage_results WHERE session_id=?", (row["session_id"],)).fetchone()
    accepted = row["status"] == "accepted" and row["doctor_id"] == doctor_id
    context = build_context(connection, row["session_id"], for_doctor=True) if accepted else None
    return {
        "id": row["id"], "status": row["status"], "created_at": row["created_at"],
        "accepted_at": row["accepted_at"], "ended_at": row["ended_at"],
        "specialty": doctors.specialty(row["specialty_code"]),
        "ended": row["ended_at"] is not None,
        "urgency": triage["urgency"] if triage else "unknown",
        "preview": {name: session[name] for name in ("age", "symptoms", "duration", "severity")},
        "patient": context["current"] if context else None,
        "previous_visits": context["previous_visits"] if context else None,
        "ai": {
            "source": triage["source"], "doctor_summary": triage["doctor_summary_fa"],
            "considerations": json.loads(triage["considerations_fa"]), "notice": AI_NOTICE,
        } if accepted and triage else None,
    }


def doctor_requests(doctor_id: str, status: str | None = None) -> list[dict]:
    expire_requests()
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        doctor = doctors.require_doctor(connection, doctor_id)
        # ponytail: this GET heartbeat is the explicit presence side effect; use a dedicated heartbeat or push presence when scaling.
        connection.execute("UPDATE doctors SET last_seen_at=? WHERE id=?", (db.utc_now(), doctor_id))
        rows = connection.execute(
            """SELECT * FROM visit_requests
               WHERE ((status='pending' AND specialty_code=? AND ?=1)
                      OR (status='accepted' AND doctor_id=?))
                 AND (? IS NULL OR status=?)
               ORDER BY created_at, rowid""",
            (doctor["specialty_code"], doctor["available"], doctor_id, status, status),
        ).fetchall()
        return [_doctor_item(connection, row, doctor_id) for row in rows]


def accept(doctor_id: str, request_id: str) -> dict:
    expire_requests()
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        doctor = doctors.require_doctor(connection, doctor_id)
        row = connection.execute(
            "SELECT * FROM visit_requests WHERE id=? AND specialty_code=?",
            (request_id, doctor["specialty_code"]),
        ).fetchone()
        if row is None:
            raise ServiceError(404, "http_404", "Not Found")
        if not doctor["available"]:
            raise ServiceError(409, "doctor_unavailable", "Doctor is unavailable")
        now = db.utc_now()
        changed = connection.execute(
            """UPDATE visit_requests SET status='accepted', doctor_id=?, accepted_at=?, updated_at=?
               WHERE id=? AND status='pending' AND specialty_code=? AND created_at>=?""",
            (doctor_id, now, now, request_id, doctor["specialty_code"], _cutoff(now)),
        ).rowcount
        if changed != 1:
            raise ServiceError(409, "request_not_pending", "Request is no longer pending")
        row = connection.execute("SELECT * FROM visit_requests WHERE id=?", (request_id,)).fetchone()
        return _doctor_item(connection, row, doctor_id)
