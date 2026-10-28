import json
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from uuid import uuid4

from app.agent.doctors import load_doctors
from app.agent.intake import PROFILE_FIELDS
from app.agent.dictionaries import match
from app.core import db, security
from app.core.config import Settings
from app.core.errors import ServiceError
from app.services.doctors import specialty


def _user(connection, user_id: str):
    row = connection.execute(
        """SELECT u.id, u.role, u.username, u.patient_id,
           d.id AS doctor_id, d.name_fa, d.specialty_code, d.verified, d.available, d.review_status, d.review_note
           FROM users u LEFT JOIN doctors d ON d.user_id=u.id WHERE u.id=?""", (user_id,),
    ).fetchone()
    return dict(row) if row else None


def public_user(user: dict) -> dict:
    return {
        "id": user["id"], "role": user["role"], "username": user["username"],
        "display_name": user["name_fa"] if user["role"] == "doctor" else "مدیر سیستم" if user["role"] == "admin" else "بیمار",
        "doctor": {
            "verified": bool(user["verified"]), "available": bool(user["available"]),
            "status": user["review_status"], "review_note": user["review_note"],
            "specialty": specialty(user["specialty_code"]),
        } if user["role"] == "doctor" else None,
    }


def _issue_session(connection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = db.utc_now()
    expires = (datetime.fromisoformat(now) + timedelta(hours=Settings().session_ttl_hours)).isoformat(timespec="microseconds")
    connection.execute(
        "INSERT INTO auth_sessions(token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (security.token_hash(token), user_id, now, expires),
    )
    return token


def register(body) -> tuple[dict, str]:
    settings = Settings()
    if body.username in {"admin", settings.admin_username, *(doctor["id"] for doctor in load_doctors()["doctors"])}:
        raise ServiceError(409, "username_unavailable", "Username unavailable")
    encoded = security.hash_password(body.password)
    user_id = uuid4().hex
    patient_id = uuid4().hex if body.role == "patient" else None
    try:
        with closing(db.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            if body.role == "doctor" and connection.execute(
                "SELECT 1 FROM doctors WHERE license_number=?", (body.license_number,)
            ).fetchone():
                raise ServiceError(409, "license_unavailable", "License number unavailable")
            now = db.utc_now()
            if patient_id:
                connection.execute("INSERT INTO patients(id, created_at) VALUES (?, ?)", (patient_id, now))
            connection.execute(
                "INSERT INTO users(id, role, username, password_hash, patient_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, body.role, body.username, encoded, patient_id, now),
            )
            if body.role == "doctor":
                connection.execute(
                    """INSERT INTO doctors(id, user_id, name_fa, specialty_code, expertise, score, verified, created_at, review_status, license_number)
                       VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)""",
                    (uuid4().hex, user_id, body.name_fa, body.specialty_code,
                     json.dumps(body.expertise, ensure_ascii=False), settings.doctor_auto_verify, now,
                     "approved" if settings.doctor_auto_verify else "pending", body.license_number),
                )
            token = _issue_session(connection, user_id)
            return _user(connection, user_id), token
    except sqlite3.IntegrityError:
        raise ServiceError(409, "username_unavailable", "Username unavailable") from None


def login(username: str, password: str) -> tuple[dict, str]:
    retry = security.login_retry_after(username)
    if retry:
        raise ServiceError(429, "http_429", "Too Many Requests", {"Retry-After": str(retry)})
    with closing(db.connect()) as connection:
        credentials = connection.execute(
            "SELECT id, role, password_hash FROM users WHERE username=?", (username,)
        ).fetchone()
    valid = security.verify_password(password, credentials["password_hash"] if credentials else security.DUMMY_HASH)
    seed_id = username in {doctor["id"] for doctor in load_doctors()["doctors"]}
    if (not valid or credentials is None or (seed_id and not Settings().demo_doctor_password)
            or (credentials["role"] == "admin" and username != Settings().admin_username)):
        security.record_failure(username)
        raise ServiceError(401, "http_401", "Unauthorized")
    security.clear_failures(username)
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        latest = connection.execute("SELECT password_hash FROM users WHERE id=?", (credentials["id"],)).fetchone()
        if latest is None or latest["password_hash"] != credentials["password_hash"]:
            raise ServiceError(401, "http_401", "Unauthorized")
        user = _user(connection, credentials["id"])
        if user is None:
            raise ServiceError(401, "http_401", "Unauthorized")
        return user, _issue_session(connection, user["id"])


# ponytail: expired auth rows are rejected on read; add periodic deletion as login volume grows.
def current_user(token: str | None):
    if not token or len(token) > 256:
        return None
    with closing(db.connect()) as connection:
        session = connection.execute(
            "SELECT user_id FROM auth_sessions WHERE token_hash=? AND expires_at>?",
            (security.token_hash(token), db.utc_now()),
        ).fetchone()
        user = _user(connection, session["user_id"]) if session else None
    if user and user["username"] in {doctor["id"] for doctor in load_doctors()["doctors"]} and not Settings().demo_doctor_password:
        return None
    if user and user["role"] == "admin" and user["username"] != Settings().admin_username:
        return None
    return user


def logout(token: str | None) -> None:
    if token:
        with closing(db.connect()) as connection, connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash=?", (security.token_hash(token),))


def _patient_profile(row) -> dict:
    profile = {name: row[name] if row else None for name in PROFILE_FIELDS}
    return {"profile": profile, "updated_at": row["updated_at"] if row else None,
            "complete": all(value is not None for value in profile.values())}


def patient_profile(patient_id: str) -> dict:
    with closing(db.connect()) as connection:
        return _patient_profile(connection.execute("SELECT * FROM patient_profiles WHERE patient_id=?", (patient_id,)).fetchone())


def update_patient_profile(patient_id: str, changes: dict) -> dict:
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT * FROM patient_profiles WHERE patient_id=?", (patient_id,)).fetchone()
        values = {**_patient_profile(row)["profile"], **changes}
        codes = json.dumps([entry["code"] for entry in match("medicines", values["medications"])]) if "medications" in changes else row["medication_codes"] if row else "[]"
        connection.execute(f"""INSERT INTO patient_profiles(patient_id,{','.join(PROFILE_FIELDS)},medication_codes,updated_at)
            VALUES (?,{','.join('?' for _ in PROFILE_FIELDS)},?,?) ON CONFLICT(patient_id) DO UPDATE SET
            {','.join(name+'=excluded.'+name for name in PROFILE_FIELDS)},
            medication_codes=excluded.medication_codes,updated_at=excluded.updated_at""",
            (patient_id, *(values[name] for name in PROFILE_FIELDS), codes, db.utc_now()))
        return _patient_profile(connection.execute("SELECT * FROM patient_profiles WHERE patient_id=?", (patient_id,)).fetchone())


def change_password(user: dict, token: str, current_password: str, new_password: str) -> None:
    if user["role"] == "admin" or user["username"] in {doctor["id"] for doctor in load_doctors()["doctors"]}:
        raise ServiceError(409, "password_managed", "Password is managed by server configuration")
    key = "pw:" + user["username"]
    retry = security.login_retry_after(key)
    if retry:
        raise ServiceError(429, "http_429", "Too Many Requests", {"Retry-After": str(retry)})
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        cookie_hash = security.token_hash(token)
        if connection.execute("SELECT 1 FROM auth_sessions WHERE token_hash=? AND user_id=? AND expires_at>?",
                              (cookie_hash, user["id"], db.utc_now())).fetchone() is None:
            raise ServiceError(401, "http_401", "Unauthorized")
        row = connection.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
        if not security.verify_password(current_password, row["password_hash"]):
            security.record_failure(key)
            raise ServiceError(401, "invalid_current_password", "Current password is incorrect")
        connection.execute("UPDATE users SET password_hash=? WHERE id=?", (security.hash_password(new_password), user["id"]))
        connection.execute("DELETE FROM auth_sessions WHERE user_id=? AND token_hash<>?", (user["id"], cookie_hash))
    security.clear_failures(key)
