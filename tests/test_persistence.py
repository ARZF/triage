import copy
import json
import logging
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core import db
from app.agent import dictionaries, sessions
from app.core.config import Settings
from app.main import app
from helpers import as_patient, intake_answers, patient_of, register_patient


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "test.db"
        self.enterContext(patch.dict(os.environ, {"APP_DB_PATH": str(self.db_path)}))
        self.client = self.enterContext(TestClient(app))
        self.user = register_patient(self.client)

    def create(self, patient_id=None):
        if patient_id is not None and self.user["patient_id"] != patient_id:
            as_patient(self.client, patient_id)
            self.user["patient_id"] = patient_id
        response = self.client.post("/v1/chat/sessions")
        self.assertEqual(response.status_code, 201)
        return response.json()

    def message(self, state, answer):
        response = self.client.post(
            "/v1/chat/sessions/" + state["session_id"] + "/messages", json={"message": answer}
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def complete(self, patient_id=None, age="30", medications="paracetamol", allergies="none"):
        state = self.create(patient_id)
        if state["step"] == "profile":
            state = self.message(state, "no")
        for answer in intake_answers(age=age, medications=medications, allergies=allergies):
            state = self.message(state, answer)
        self.assertTrue(state["done"])
        return state

    def row(self, session_id):
        with closing(db.connect()) as connection:
            return connection.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()

    def test_new_patient_persists_data_codes_and_ordered_messages(self):
        state = self.complete()
        self.assertFalse(state["returning"])
        self.assertNotIn("returning_profile", state)
        with closing(db.connect()) as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id=?", (state["session_id"],)).fetchone()
            self.assertEqual(row["patient_id"], patient_of(state))
            self.assertEqual(row["age"], 30)
            self.assertEqual(row["symptoms"], "cough")
            self.assertEqual(json.loads(row["symptom_codes"]), ["cough"])
            self.assertEqual(json.loads(row["medication_codes"]), ["acetaminophen"])
            messages = connection.execute(
                "SELECT role, content, created_at FROM messages WHERE session_id=? ORDER BY id",
                (state["session_id"],),
            ).fetchall()
            self.assertEqual([m["role"] for m in messages], ["bot"] + ["user", "bot"] * 14)
            self.assertEqual(messages[1]["content"], "30")
            self.assertEqual(messages[-1]["content"], state["reply"])
            for value in (row["created_at"], row["updated_at"], messages[0]["created_at"]):
                self.assertEqual(datetime.fromisoformat(value).utcoffset(), timedelta(0))
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 5)

    def test_returning_profile_yes_prefills_and_skips_questions(self):
        first = self.complete(allergies="synthetic allergy")
        state = self.create(patient_of(first))
        self.assertTrue(state["returning"])
        self.assertEqual(state["step"], "profile")
        self.assertEqual(state["collected"], {
            "age": 30, "symptoms": None, "duration": None, "severity": None,
            "medications": "paracetamol", "allergies": "synthetic allergy",
            "height_cm": 170.5, "weight_kg": 70.2, "chief_complaint": None,
            "medical_history": "none", "medication_history": "none", "food_allergies": "none",
            "additional_context": None,
        })
        self.assertIn("۳۰", state["reply"])
        self.assertIn("paracetamol", state["reply"])
        self.assertIn("synthetic allergy", state["reply"])
        invalid = self.message(state, "maybe")
        self.assertEqual(invalid["step"], "profile")
        self.assertEqual(invalid["collected"], state["collected"])
        state = self.message(state, "بله")
        self.assertEqual(state["step"], "chief_complaint")
        state = self.message(state, "another synthetic complaint")
        self.assertEqual(self.row(state["session_id"])["returning_profile"], 1)
        for answer, step in (("fever", "duration"), ("one day", "severity"), ("4", "additional_context"), ("رد کردن", "confirm")):
            state = self.message(state, answer)
            self.assertEqual(state["step"], step)
        state = self.message(state, "yes")
        self.assertTrue(state["done"])
        self.assertEqual(state["collected"]["medications"], "paracetamol")
        self.assertEqual(json.loads(self.row(state["session_id"])["medication_codes"]), ["acetaminophen"])

    def test_profile_no_discards_prefill_and_runs_full_intake(self):
        previous = self.complete()
        state = self.create(patient_of(previous))
        state = self.message(state, "خیر")
        self.assertEqual(state["step"], "age")
        self.assertTrue(all(value is None for value in state["collected"].values()))
        self.assertEqual(self.row(state["session_id"])["returning_profile"], 0)
        for answer, next_step in zip(
            intake_answers(age="45", severity="4", medications="ibuprofen"),
            ("height_cm", "weight_kg", "chief_complaint", "symptoms", "duration", "severity", "medical_history", "medications", "medication_history", "food_allergies", "allergies", "additional_context", "confirm", "confirm"),
        ):
            state = self.message(state, answer)
            self.assertEqual(state["step"], next_step)
        self.assertTrue(state["done"])
        self.assertEqual(state["collected"]["age"], 45)
        self.assertEqual(state["collected"]["medications"], "ibuprofen")
        latest = self.create(patient_of(previous))
        self.assertEqual(latest["collected"]["age"], 45)
        self.assertEqual(latest["collected"]["medications"], "ibuprofen")

    def test_emergency_and_unfinished_visits_do_not_qualify(self):
        for emergency in (False, True):
            with self.subTest(emergency=emergency):
                state = self.create()
                state = self.message(state, "30")
                if emergency:
                    for answer in ("170.5", "70.2", "synthetic complaint"):
                        state = self.message(state, answer)
                    state = self.message(state, "CHEST PAIN")
                    self.assertTrue(state["emergency"])
                new = self.create(patient_of(state))
                self.assertFalse(new["returning"])
                self.assertEqual(new["step"], "age")
                self.assertTrue(all(value is None for value in new["collected"].values()))

    def test_red_flag_text_is_absent_from_every_table(self):
        state = self.create()
        for answer in intake_answers()[:4]:
            state = self.message(state, answer)
        original = "unique_redaction_marker CHEST PAIN"
        state = self.message(state, original)
        self.assertTrue(state["done"])
        self.assertIsNone(state["collected"]["symptoms"])
        with closing(db.connect()) as connection:
            for table in ("patients", "sessions", "messages"):
                for row in connection.execute(f"SELECT * FROM {table}"):
                    self.assertFalse(any(original in value for value in row if isinstance(value, str)))
            contents = [row[0] for row in connection.execute(
                "SELECT content FROM messages WHERE session_id=? AND role='user' ORDER BY id",
                (state["session_id"],),
            )]
            self.assertEqual(contents[-1], sessions.REDACTED_MESSAGE)
            self.assertEqual(json.loads(self.row(state["session_id"])["symptom_codes"]), [])

    def test_completed_session_never_changes_or_appends_messages(self):
        state = self.complete()
        before = dict(self.row(state["session_id"]))
        history_before = self.client.get("/v1/me/history").json()
        self.assertEqual(self.message(state, "ignored synthetic answer"), state)
        self.assertEqual(dict(self.row(state["session_id"])), before)
        self.assertEqual(self.client.get("/v1/me/history").json(), history_before)
        self.create(patient_of(state))
        self.assertEqual(self.message(state, "ignored again"), state)

    def test_history_order_limit_messages_and_unknown_patient(self):
        state = self.complete()
        ids = [state["session_id"]]
        for _ in range(11):
            ids.append(self.create(patient_of(state))["session_id"])
        path = "/v1/me/history"
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([visit["session_id"] for visit in response.json()], list(reversed(ids))[:10])
        self.assertEqual(len(self.client.get(path, params={"limit": 50}).json()), 12)
        visit = self.client.get(path, params={"limit": 1}).json()[0]
        self.assertEqual(set(visit), {"session_id", "created_at", "done", "emergency", "collected", "matched", "messages"})
        self.assertEqual(visit["messages"][0]["role"], "bot")
        for limit in (0, 51, "bad"):
            response = self.client.get(path, params={"limit": limit})
            self.assertEqual(response.status_code, 422)
            self.assertIn("error", response.json())
        self.assertEqual(self.client.get("/v1/patients/unknown/history").status_code, 404)

    def test_history_uses_stored_codes_even_if_dictionary_changes(self):
        state = self.complete()
        loaded = copy.deepcopy(dictionaries.load_dictionaries())
        loaded["symptoms"] = [entry for entry in loaded["symptoms"] if entry["code"] != "cough"]
        loaded["medicines"] = [entry for entry in loaded["medicines"] if entry["code"] != "acetaminophen"]
        with patch.object(dictionaries, "load_dictionaries", return_value=loaded):
            response = self.client.get("/v1/me/history")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["matched"], {
            "symptoms": [{"code": "cough", "name_fa": "cough"}],
            "medicines": [{"code": "acetaminophen", "name_fa": "acetaminophen"}],
        })

    def test_delete_cascades_and_unknown_ids_return_404(self):
        state = self.complete()
        self.create(patient_of(state))
        response = self.client.delete("/v1/me")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        with closing(db.connect()) as connection:
            for table in ("patients", "sessions", "messages"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual(self.client.delete("/v1/me").status_code, 401)
        self.assertEqual(self.client.get("/v1/me/history").status_code, 401)
        self.assertEqual(self.client.post(
            f"/v1/chat/sessions/{state['session_id']}/messages", json={"message": "synthetic"}
        ).status_code, 401)

    def test_old_patient_routes_removed_and_creation_body_rejected(self):
        self.assertEqual(self.client.get("/v1/patients/unknown/history").status_code, 404)
        self.assertEqual(self.client.delete("/v1/patients/unknown").status_code, 404)
        for patient_id in ("unknown", "x" * 65, 42, None):
            response = self.client.post("/v1/chat/sessions", json={"patient_id": patient_id})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.post("/v1/chat/sessions").status_code, 201)

    def test_connection_path_is_read_fresh_without_lifespan(self):
        alternate = self.db_path.with_name("alternate.db")
        with patch.dict(os.environ, {"APP_DB_PATH": str(alternate)}):
            with TestClient(app) as client:
                register_patient(client)
                self.assertEqual(client.post("/v1/chat/sessions").status_code, 201)
            with closing(db.connect()) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0], 1)
        bare = TestClient(app)
        self.addCleanup(bare.close)
        untouched = self.db_path.with_name("no-lifespan.db")
        with patch.dict(os.environ, {"APP_DB_PATH": str(untouched)}):
            register_patient(bare)
            self.assertEqual(bare.post("/v1/chat/sessions").status_code, 201)
        self.assertTrue(untouched.exists())
        with patch.dict(os.environ, {"APP_DB_PATH": " "}):
            with self.assertRaises(ValueError):
                db.connect()
        self.assertEqual(Settings().db_path, str(self.db_path))

    def test_one_closed_connection_per_request(self):
        actual = db.connect
        opened = []
        def track():
            connection = actual()
            opened.append(connection)
            return connection
        with patch.object(db, "connect", side_effect=track):
            state = self.create(self.user["patient_id"])
            self.message(state, "30")
            self.client.get("/v1/me/history")
            self.client.delete("/v1/me")
        self.assertEqual(len(opened), 9)
        for connection in opened:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_temp_database_can_be_deleted_while_app_is_running(self):
        self.create()
        self.db_path.unlink()
        self.assertFalse(self.db_path.exists())

    def test_failed_message_rolls_back_session_and_both_messages(self):
        state = self.create()
        before = dict(self.row(state["session_id"]))
        original = db.add_message
        def fail_after_insert(connection, session_id, role, content, timestamp):
            original(connection, session_id, role, content, timestamp)
            if role == "bot":
                raise sqlite3.OperationalError("synthetic storage failure")
        with patch.object(db, "add_message", side_effect=fail_after_insert):
            response = self.client.post(
                f"/v1/chat/sessions/{state['session_id']}/messages", json={"message": "30"}
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": {"code": "storage_error", "message": "Storage operation failed"}})
        self.assertEqual(dict(self.row(state["session_id"])), before)
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)

    def test_failed_creation_rolls_back_session_without_changing_account(self):
        with closing(db.connect()) as connection:
            before = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in ("patients", "users", "auth_sessions", "sessions", "messages")}
        with patch.object(db, "add_message", side_effect=sqlite3.OperationalError("synthetic failure")):
            response = self.client.post("/v1/chat/sessions")
        self.assertEqual(response.status_code, 500)
        with closing(db.connect()) as connection:
            after = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in before}
        self.assertEqual(after, before)

    def test_concurrent_messages_are_serialized(self):
        state = self.create()
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(lambda _: sessions.send_message(state["session_id"], "30"), range(2)))
        self.assertEqual({row["step"] for row in rows}, {"height_cm", "weight_kg"})
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 5)

    def test_access_logging_is_disabled(self):
        self.assertTrue(logging.getLogger("uvicorn.access").disabled)

    def test_initialization_failure_closes_connection(self):
        fresh = self.db_path.with_name("initialization-failure.db")
        with patch.dict(os.environ, {"APP_DB_PATH": str(fresh)}), patch.object(db, "SCHEMA", "invalid synthetic SQL"):
            with self.assertRaises(sqlite3.Error):
                db.connect()
        fresh.unlink()
        self.assertFalse(fresh.exists())

    def test_v3_migration_preserves_records_and_recollects_missing_profile_fields(self):
        state = self.complete()
        added = ("height_cm", "weight_kg", "chief_complaint", "medical_history", "medication_history", "food_allergies", "additional_context")
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in ("users", "patients", "sessions", "auth_sessions", "messages", "doctors")}
            for name in added:
                connection.execute(f"ALTER TABLE sessions DROP COLUMN {name}")
            connection.execute("PRAGMA user_version=3")
        with ThreadPoolExecutor(max_workers=2) as pool:
            def migrate(_):
                with closing(db.connect()) as connection:
                    return connection.execute("PRAGMA user_version").fetchone()[0]
            self.assertEqual(list(pool.map(migrate, range(2))), [5, 5])
        with closing(db.connect()) as connection:
            for table, count in counts.items():
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], count)
            row = connection.execute("SELECT * FROM sessions WHERE id=?", (state["session_id"],)).fetchone()
            self.assertEqual(row["medications"], "paracetamol")
            self.assertTrue(all(row[name] is None for name in added))
        self.assertEqual(self.client.get("/v1/auth/me").status_code, 200)
        history = self.client.get("/v1/me/history").json()[0]
        self.assertIsNone(history["collected"]["height_cm"])
        new = self.create()
        self.assertTrue(new["returning"])
        self.assertEqual(new["step"], "age")
        self.assertTrue(all(value is None for value in new["collected"].values()))
        self.assertEqual(new["matched"]["medicines"], [])

    def test_failed_column_migration_rolls_back_and_can_retry(self):
        path = self.db_path.with_name("migration-failure.db")
        with closing(sqlite3.connect(path)) as connection:
            connection.executescript(db.SCHEMA)
        original = sqlite3.connect
        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, *args):
                if sql.startswith("ALTER TABLE sessions ADD COLUMN weight_kg"):
                    raise sqlite3.OperationalError("synthetic migration failure")
                return super().execute(sql, *args)
        def connect(*args, **kwargs):
            return original(*args, **kwargs, factory=FailingConnection)
        with patch.dict(os.environ, {"APP_DB_PATH": str(path)}):
            with patch.object(db.sqlite3, "connect", side_effect=connect):
                with self.assertRaises(sqlite3.OperationalError):
                    db.connect()
            with closing(original(path)) as connection:
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)
                self.assertNotIn("height_cm", {row[1] for row in connection.execute("PRAGMA table_info(sessions)")})
            with closing(db.connect()) as connection:
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 5)

    def test_new_intake_fields_round_trip_in_history_and_complaint_is_redacted(self):
        state = self.create()
        answers = ("۳۰", "۱۷۰٫۵", "٧٠.٢", "شکایت ساختگی", "سرفه، تب", "دو روز", "۳",
                   "بیماری ساختگی", "هیچ", "داروی قبلی ساختگی", "حساسیت غذایی ساختگی", "حساسیت دارویی ساختگی", "توضیح ساختگی برای پزشک", "بله")
        for answer in answers:
            state = self.message(state, answer)
        self.assertTrue(state["done"])
        history = self.client.get("/v1/me/history").json()[0]
        self.assertEqual(history["collected"], state["collected"])
        self.assertEqual(state["collected"]["medical_history"], "بیماری ساختگی")
        self.assertEqual(state["collected"]["medication_history"], "داروی قبلی ساختگی")
        self.assertEqual(state["collected"]["food_allergies"], "حساسیت غذایی ساختگی")
        self.assertEqual(state["collected"]["allergies"], "حساسیت دارویی ساختگی")
        new = self.create()
        self.assertEqual(new["step"], "profile")
        new = self.message(new, "بله")
        self.assertEqual(new["step"], "chief_complaint")
        original = "unique_complaint_marker CHEST PAIN"
        new = self.message(new, original)
        self.assertTrue(new["emergency"])
        self.assertIsNone(new["collected"]["chief_complaint"])
        self.assertNotIn(original, json.dumps(self.client.get("/v1/me/history").json()))

    def test_v4_note_migration_preserves_data_and_rolls_back_failure(self):
        state = self.complete()
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("ALTER TABLE sessions DROP COLUMN additional_context")
            connection.execute("PRAGMA user_version=4")
        original = sqlite3.connect
        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, *args):
                if sql == "PRAGMA user_version=5":
                    raise sqlite3.OperationalError("synthetic migration failure")
                return super().execute(sql, *args)
        with patch.object(db.sqlite3, "connect", side_effect=lambda *args, **kwargs: original(*args, **kwargs, factory=FailingConnection)):
            with self.assertRaises(sqlite3.OperationalError):
                db.connect()
        with closing(original(self.db_path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertNotIn("additional_context", {row[1] for row in connection.execute("PRAGMA table_info(sessions)")})
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 5)
            row = connection.execute("SELECT * FROM sessions WHERE id=?", (state["session_id"],)).fetchone()
            self.assertEqual(row["medications"], "paracetamol")
            self.assertIsNone(row["additional_context"])
        self.assertEqual(self.client.get("/v1/auth/me").status_code, 200)

    def test_concurrent_review_edits_do_not_lose_other_fields(self):
        state = self.create()
        for answer in intake_answers()[:-1]:
            state = self.message(state, answer)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda item: sessions.send_message(state["session_id"], item[1], item[0]),
                          (("age", "40"), ("height_cm", "180"))))
        row = self.row(state["session_id"])
        self.assertEqual(row["age"], 40)
        self.assertEqual(row["height_cm"], 180)
        self.assertEqual(row["step"], "confirm")
        self.assertFalse(row["done"])
