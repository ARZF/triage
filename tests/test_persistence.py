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


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "test.db"
        self.enterContext(patch.dict(os.environ, {"APP_DB_PATH": str(self.db_path)}))
        self.client = self.enterContext(TestClient(app))

    def create(self, patient_id=None):
        response = (
            self.client.post("/v1/chat/sessions")
            if patient_id is None else self.client.post("/v1/chat/sessions", json={"patient_id": patient_id})
        )
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
        for answer in (age, "cough", "two days", "3", medications, allergies, "yes"):
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
            self.assertEqual(row["patient_id"], state["patient_id"])
            self.assertEqual(row["age"], 30)
            self.assertEqual(row["symptoms"], "cough")
            self.assertEqual(json.loads(row["symptom_codes"]), ["cough"])
            self.assertEqual(json.loads(row["medication_codes"]), ["acetaminophen"])
            messages = connection.execute(
                "SELECT role, content, created_at FROM messages WHERE session_id=? ORDER BY id",
                (state["session_id"],),
            ).fetchall()
            self.assertEqual([m["role"] for m in messages], ["bot"] + ["user", "bot"] * 7)
            self.assertEqual(messages[1]["content"], "30")
            self.assertEqual(messages[-1]["content"], state["reply"])
            for value in (row["created_at"], row["updated_at"], messages[0]["created_at"]):
                self.assertEqual(datetime.fromisoformat(value).utcoffset(), timedelta(0))
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_returning_profile_yes_prefills_and_skips_questions(self):
        first = self.complete(allergies="synthetic allergy")
        state = self.create(first["patient_id"])
        self.assertTrue(state["returning"])
        self.assertEqual(state["step"], "profile")
        self.assertEqual(state["collected"], {
            "age": 30, "symptoms": None, "duration": None, "severity": None,
            "medications": "paracetamol", "allergies": "synthetic allergy",
        })
        self.assertIn("۳۰", state["reply"])
        self.assertIn("paracetamol", state["reply"])
        self.assertIn("synthetic allergy", state["reply"])
        invalid = self.message(state, "maybe")
        self.assertEqual(invalid["step"], "profile")
        self.assertEqual(invalid["collected"], state["collected"])
        state = self.message(state, "بله")
        self.assertEqual(state["step"], "symptoms")
        self.assertEqual(self.row(state["session_id"])["returning_profile"], 1)
        for answer, step in (("fever", "duration"), ("one day", "severity"), ("4", "confirm")):
            state = self.message(state, answer)
            self.assertEqual(state["step"], step)
        state = self.message(state, "yes")
        self.assertTrue(state["done"])
        self.assertEqual(state["collected"]["medications"], "paracetamol")
        self.assertEqual(json.loads(self.row(state["session_id"])["medication_codes"]), ["acetaminophen"])

    def test_profile_no_discards_prefill_and_runs_full_intake(self):
        previous = self.complete()
        state = self.create(previous["patient_id"])
        state = self.message(state, "خیر")
        self.assertEqual(state["step"], "age")
        self.assertTrue(all(value is None for value in state["collected"].values()))
        self.assertEqual(self.row(state["session_id"])["returning_profile"], 0)
        for answer, next_step in zip(
            ("45", "cough", "two days", "4", "ibuprofen", "none", "yes"),
            ("symptoms", "duration", "severity", "medications", "allergies", "confirm", "confirm"),
        ):
            state = self.message(state, answer)
            self.assertEqual(state["step"], next_step)
        self.assertTrue(state["done"])
        self.assertEqual(state["collected"]["age"], 45)
        self.assertEqual(state["collected"]["medications"], "ibuprofen")
        latest = self.create(previous["patient_id"])
        self.assertEqual(latest["collected"]["age"], 45)
        self.assertEqual(latest["collected"]["medications"], "ibuprofen")

    def test_emergency_and_unfinished_visits_do_not_qualify(self):
        for emergency in (False, True):
            with self.subTest(emergency=emergency):
                state = self.create()
                state = self.message(state, "30")
                if emergency:
                    state = self.message(state, "CHEST PAIN")
                    self.assertTrue(state["emergency"])
                new = self.create(state["patient_id"])
                self.assertFalse(new["returning"])
                self.assertEqual(new["step"], "age")
                self.assertTrue(all(value is None for value in new["collected"].values()))

    def test_red_flag_text_is_absent_from_every_table(self):
        state = self.message(self.create(), "30")
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
        history_before = self.client.get(f"/v1/patients/{state['patient_id']}/history").json()
        self.assertEqual(self.message(state, "ignored synthetic answer"), state)
        self.assertEqual(dict(self.row(state["session_id"])), before)
        self.assertEqual(self.client.get(f"/v1/patients/{state['patient_id']}/history").json(), history_before)
        self.create(state["patient_id"])
        self.assertEqual(self.message(state, "ignored again"), state)

    def test_history_order_limit_messages_and_unknown_patient(self):
        state = self.complete()
        ids = [state["session_id"]]
        for _ in range(11):
            ids.append(self.create(state["patient_id"])["session_id"])
        path = f"/v1/patients/{state['patient_id']}/history"
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
            response = self.client.get(f"/v1/patients/{state['patient_id']}/history")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["matched"], {
            "symptoms": [{"code": "cough", "name_fa": "cough"}],
            "medicines": [{"code": "acetaminophen", "name_fa": "acetaminophen"}],
        })

    def test_delete_cascades_and_unknown_ids_return_404(self):
        state = self.complete()
        self.create(state["patient_id"])
        response = self.client.delete(f"/v1/patients/{state['patient_id']}")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        with closing(db.connect()) as connection:
            for table in ("patients", "sessions", "messages"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual(self.client.delete(f"/v1/patients/{state['patient_id']}").status_code, 404)
        self.assertEqual(self.client.get(f"/v1/patients/{state['patient_id']}/history").status_code, 404)
        self.assertEqual(self.client.post(
            f"/v1/chat/sessions/{state['session_id']}/messages", json={"message": "synthetic"}
        ).status_code, 404)

    def test_unknown_patient_and_invalid_creation_body(self):
        response = self.client.post("/v1/chat/sessions", json={"patient_id": "unknown"})
        self.assertEqual(response.status_code, 404)
        for patient_id in ("x" * 65, 42):
            response = self.client.post("/v1/chat/sessions", json={"patient_id": patient_id})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.post("/v1/chat/sessions").status_code, 201)
        self.assertEqual(self.client.post("/v1/chat/sessions", json={"patient_id": None}).status_code, 201)

    def test_connection_path_is_read_fresh_without_lifespan(self):
        alternate = self.db_path.with_name("alternate.db")
        with patch.dict(os.environ, {"APP_DB_PATH": str(alternate)}):
            with TestClient(app) as client:
                self.assertEqual(client.post("/v1/chat/sessions").status_code, 201)
            with closing(db.connect()) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0], 1)
        bare = TestClient(app)
        self.addCleanup(bare.close)
        untouched = self.db_path.with_name("no-lifespan.db")
        with patch.dict(os.environ, {"APP_DB_PATH": str(untouched)}):
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
            state = self.create()
            self.message(state, "30")
            self.client.get(f"/v1/patients/{state['patient_id']}/history")
            self.client.delete(f"/v1/patients/{state['patient_id']}")
        self.assertEqual(len(opened), 4)
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

    def test_failed_creation_rolls_back_patient_and_session(self):
        with patch.object(db, "add_message", side_effect=sqlite3.OperationalError("synthetic failure")):
            response = self.client.post("/v1/chat/sessions")
        self.assertEqual(response.status_code, 500)
        with closing(db.connect()) as connection:
            for table in ("patients", "sessions", "messages"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_concurrent_messages_are_serialized(self):
        state = self.create()
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(lambda _: sessions.send_message(state["session_id"], "30"), range(2)))
        self.assertEqual({row["step"] for row in rows}, {"symptoms", "duration"})
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 5)

    def test_access_logging_is_disabled(self):
        self.assertTrue(logging.getLogger("uvicorn.access").disabled)

    def test_initialization_failure_closes_connection(self):
        with patch.object(db, "SCHEMA", "invalid synthetic SQL"):
            with self.assertRaises(sqlite3.Error):
                db.connect()
        self.db_path.unlink()
        self.assertFalse(self.db_path.exists())
