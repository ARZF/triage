import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, replace
from uuid import uuid4

from app.core import db
from app.core.errors import ServiceError
from app.agent import dictionaries
from app.agent.intake import PROFILE_FIELDS, QUESTIONS, Collected, IntakeState, advance, profile_state

REDACTED_MESSAGE = "متن این پیام به‌دلیل توقف اضطراری ذخیره نشده است."


def restore(row: sqlite3.Row) -> IntakeState:
    return IntakeState(
        step=row["step"], done=bool(row["done"]), emergency=bool(row["emergency"]),
        returning_profile=bool(row["returning_profile"]), reply=row["reply"],
        collected=Collected(**{name: row[name] for name in Collected.__dataclass_fields__}),
    )


def _values(state: IntakeState) -> dict:
    values = asdict(state)
    values.update(values.pop("collected"))
    return values


def _read(connection: sqlite3.Connection, session_id: str) -> sqlite3.Row:
    # Qualifying completions at creation time keep returning stable for this session.
    row = connection.execute(
        """SELECT s.*, EXISTS(
            SELECT 1 FROM sessions previous
            WHERE previous.patient_id=s.patient_id AND previous.id<>s.id
              AND previous.done=1 AND previous.emergency=0
              AND previous.updated_at<=s.created_at
        ) AS "returning" FROM sessions s WHERE s.id=?""",
        (session_id,),
    ).fetchone()
    if row is None:
        raise KeyError(session_id)
    return row


def create_session(patient_id: str | None = None) -> sqlite3.Row:
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        now = db.utc_now()
        if patient_id is None:
            patient_id = uuid4().hex
            connection.execute("INSERT INTO patients(id, created_at) VALUES (?, ?)", (patient_id, now))
        elif connection.execute("SELECT 1 FROM patients WHERE id=?", (patient_id,)).fetchone() is None:
            raise KeyError(patient_id)
        previous = connection.execute(
            """SELECT * FROM sessions WHERE patient_id=? AND done=1 AND emergency=0
               ORDER BY updated_at DESC, created_at DESC, rowid DESC LIMIT 1""",
            (patient_id,),
        ).fetchone()
        has_profile = previous is not None and all(previous[name] is not None for name in PROFILE_FIELDS)
        state = profile_state(Collected(**{name: previous[name] for name in PROFILE_FIELDS})) if has_profile else IntakeState()
        session_id = uuid4().hex
        values = {
            **_values(state), "id": session_id, "patient_id": patient_id,
            "symptom_codes": "[]",
            "medication_codes": previous["medication_codes"] if has_profile else "[]",
            "created_at": now, "updated_at": now,
        }
        connection.execute(
            """INSERT INTO sessions(
                id, patient_id, step, done, emergency, returning_profile,
                age, symptoms, duration, severity, medications, allergies,
                height_cm, weight_kg, chief_complaint, medical_history, medication_history, food_allergies, additional_context,
                symptom_codes, medication_codes, reply, created_at, updated_at
            ) VALUES (
                :id, :patient_id, :step, :done, :emergency, :returning_profile,
                :age, :symptoms, :duration, :severity, :medications, :allergies,
                :height_cm, :weight_kg, :chief_complaint, :medical_history, :medication_history, :food_allergies, :additional_context,
                :symptom_codes, :medication_codes, :reply, :created_at, :updated_at
            )""",
            values,
        )
        db.add_message(connection, session_id, "bot", state.reply, now)
        return _read(connection, session_id)


def send_message(session_id: str, message: str, edit_field: str | None = None) -> sqlite3.Row:
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = _read(connection, session_id)
        previous = restore(row)
        if edit_field is not None and (previous.done or previous.step != "confirm"):
            raise ServiceError(409, "edit_not_allowed", "Answers can only be edited during final review")
        if previous.done:
            return row
        if edit_field is None:
            state, reply = advance(previous, message)
        else:
            if edit_field not in Collected.__dataclass_fields__:
                raise ServiceError(422, "invalid_answer_field", "Invalid answer field")
            state, reply = advance(replace(previous, step=edit_field, returning_profile=False), message)
            if state.step == edit_field and not state.done:
                raise ServiceError(422, "invalid_answer", "Invalid answer")
            if not state.emergency:
                state = replace(state, step="confirm", returning_profile=previous.returning_profile, reply=QUESTIONS["confirm"])
                reply = state.reply
        codes = {"symptom_codes": row["symptom_codes"], "medication_codes": row["medication_codes"]}
        for field, kind, column in (
            ("symptoms", "symptoms", "symptom_codes"),
            ("medications", "medicines", "medication_codes"),
        ):
            answer = getattr(state.collected, field)
            if answer != getattr(previous.collected, field):
                codes[column] = json.dumps([entry["code"] for entry in dictionaries.match(kind, answer or "")])
        now = db.utc_now()
        connection.execute(
            """UPDATE sessions SET
                step=:step, done=:done, emergency=:emergency, returning_profile=:returning_profile,
                age=:age, symptoms=:symptoms, duration=:duration, severity=:severity,
                medications=:medications, allergies=:allergies, symptom_codes=:symptom_codes,
                height_cm=:height_cm, weight_kg=:weight_kg, chief_complaint=:chief_complaint,
                medical_history=:medical_history, medication_history=:medication_history, food_allergies=:food_allergies,
                additional_context=:additional_context,
                medication_codes=:medication_codes, reply=:reply, updated_at=:updated_at
                WHERE id=:id""",
            {**_values(state), **codes, "updated_at": now, "id": session_id},
        )
        content = REDACTED_MESSAGE if state.emergency and not previous.emergency else message
        db.add_message(connection, session_id, "user", content, now)
        db.add_message(connection, session_id, "bot", reply, now)
        return _read(connection, session_id)


def patient_history(patient_id: str, limit: int = 10) -> list[dict]:
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN")
        if connection.execute("SELECT 1 FROM patients WHERE id=?", (patient_id,)).fetchone() is None:
            raise KeyError(patient_id)
        rows = connection.execute(
            "SELECT * FROM sessions WHERE patient_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (patient_id, limit),
        ).fetchall()
        loaded = dictionaries.load_dictionaries()
        names = {
            kind: {entry["code"]: entry["name_fa"] for entry in entries}
            for kind, entries in loaded.items()
        }
        visits = []
        # ponytail: at most 50 per-visit message queries; batch-fetch messages if history limits grow.
        for row in rows:
            state = restore(row)
            matched = {
                kind: [{"code": code, "name_fa": names[kind].get(code, code)} for code in json.loads(row[column])]
                for kind, column in (("symptoms", "symptom_codes"), ("medicines", "medication_codes"))
            }
            visits.append({
                "session_id": row["id"], "created_at": row["created_at"],
                "done": state.done, "emergency": state.emergency,
                "collected": asdict(state.collected), "matched": matched,
                "messages": [dict(message) for message in connection.execute(
                    "SELECT role, content, created_at FROM messages WHERE session_id=? ORDER BY id",
                    (row["id"],),
                )],
            })
        return visits


def delete_patient(patient_id: str) -> None:
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        result = connection.execute("DELETE FROM patients WHERE id=?", (patient_id,))
        if result.rowcount == 0:
            raise KeyError(patient_id)
