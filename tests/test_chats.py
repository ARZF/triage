import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier, Lock
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core import db, llm
from app.core.errors import ServiceError
from app.main import app
from app.services import accounts, chats
from helpers import intake_answers, register_doctor, register_patient

BASE = "2030-01-01T00:00:00.000000+00:00"


class ChatTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(directory) / "chats.db"
        self.enterContext(patch.dict(os.environ, {
            "APP_DB_PATH": str(self.path), "APP_DOCTOR_AUTO_VERIFY": "true", "APP_DEMO_DOCTOR_PASSWORD": "",
            "APP_LLM_BASE_URL": "", "APP_LLM_MODEL": "", "APP_SESSION_TTL_HOURS": "12", "APP_REQUEST_TTL_MINUTES": "30",
        }))
        self.clock = self.enterContext(patch.object(db, "utc_now", return_value=BASE))
        self.patient = self.enterContext(TestClient(app))
        self.patient_user = register_patient(self.patient)
        self.doctor = TestClient(app)
        self.addCleanup(self.doctor.close)
        self.doctor_row = register_doctor(self.doctor)
        self.doctor.get("/v1/doctor/requests")
        state = self.patient.post("/v1/chat/sessions").json()
        self.session_id = state["session_id"]
        for answer in intake_answers():
            self.assertEqual(self.patient.post(f"/v1/chat/sessions/{self.session_id}/messages", json={"message": answer}).status_code, 200)
        self.patient.post(f"/v1/chat/sessions/{self.session_id}/triage")
        self.visit_id = self.patient.post("/v1/visit-requests", json={"session_id": self.session_id}).json()["id"]
        self.assertEqual(self.doctor.post(f"/v1/doctor/requests/{self.visit_id}/accept").status_code, 200)
        self.url = f"/v1/visit-requests/{self.visit_id}"

    def send(self, client, content):
        return client.post(self.url + "/messages", json={"content": content})

    def snapshot(self):
        with closing(db.connect()) as connection:
            tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {name: [tuple(row) for row in connection.execute(f'SELECT * FROM "{name}"')] for name in tables}

    def test_two_sided_exchange_projection_no_store_and_no_llm(self):
        with patch.object(llm, "chat_completion") as provider, self.assertNoLogs("app", level="DEBUG"):
            first = self.send(self.patient, "  synthetic patient message\nsecond line  ")
            second = self.send(self.doctor, "synthetic doctor reply")
        provider.assert_not_called()
        for response, sender in ((first, "patient"), (second, "doctor")):
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(set(response.json()), {"id", "sender", "content", "created_at"})
            self.assertEqual(response.json()["sender"], sender)
        self.assertEqual(first.json()["content"], "synthetic patient message\nsecond line")
        for client in (self.patient, self.doctor):
            response = client.get(self.url + "/messages")
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.json(), {"messages": [first.json(), second.json()], "ended": False, "has_more": False})
            for value in (self.patient_user["id"], self.patient_user["patient_id"], self.patient_user["username"],
                          self.doctor_row["id"], self.doctor_row["user_id"], self.session_id, "username", "patient_id", "request_id"):
                self.assertNotIn(value, response.text)

    def test_participation_and_role_boundaries(self):
        other_patient, other_doctor, unverified, anonymous = [TestClient(app) for _ in range(4)]
        for client in (other_patient, other_doctor, unverified, anonymous):
            self.addCleanup(client.close)
        register_patient(other_patient)
        register_doctor(other_doctor)
        with patch.dict(os.environ, {"APP_DOCTOR_AUTO_VERIFY": "false"}):
            register_doctor(unverified)
        for client, message_status, end_status in ((other_patient, 404, 403), (other_doctor, 404, 404), (unverified, 404, 403), (anonymous, 401, 401)):
            for response in (client.get(self.url + "/messages"), self.send(client, "synthetic")):
                self.assertEqual(response.status_code, message_status)
                self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(client.post(self.url + "/end").status_code, end_status)
        self.assertEqual(self.patient.post(self.url + "/end").status_code, 403)
        for client in (self.patient, self.doctor):
            self.assertEqual(client.get("/v1/visit-requests/unknown/messages").status_code, 404)
            self.assertEqual(client.post("/v1/visit-requests/unknown/messages", json={"content": "synthetic"}).status_code, 404)
        self.assertEqual(self.doctor.post("/v1/visit-requests/unknown/end").status_code, 404)
        with closing(db.connect()) as connection, connection:
            connection.execute("UPDATE doctors SET verified=0, review_status='suspended' WHERE id=?", (self.doctor_row["id"],))
        self.assertEqual(self.doctor.get(self.url + "/messages").status_code, 404)

    def test_unaccepted_requests_are_hidden(self):
        for status in ("pending", "cancelled", "expired"):
            with closing(db.connect()) as connection, connection:
                connection.execute("UPDATE visit_requests SET status=?, doctor_id=NULL WHERE id=?", (status, self.visit_id))
            for client in (self.patient, self.doctor):
                self.assertEqual(client.get(self.url + "/messages").status_code, 404)
                self.assertEqual(self.send(client, "synthetic").status_code, 404)
            self.assertEqual(self.doctor.post(self.url + "/end").status_code, 404)

    def test_pagination_order_cursor_limits_and_has_more(self):
        with closing(db.connect()) as connection, connection:
            connection.executemany("INSERT INTO visit_messages(request_id,sender_role,content,created_at) VALUES (?,'patient',?,?)",
                                   [(self.visit_id, f"synthetic {index}", BASE) for index in range(105)])
        first = self.patient.get(self.url + "/messages").json()
        self.assertEqual(len(first["messages"]), 50)
        self.assertTrue(first["has_more"])
        cursor = first["messages"][-1]["id"]
        second = self.doctor.get(self.url + "/messages", params={"after": cursor, "limit": 100}).json()
        self.assertEqual(len(second["messages"]), 55)
        self.assertFalse(second["has_more"])
        messages = first["messages"] + second["messages"]
        self.assertEqual([message["id"] for message in messages], sorted({message["id"] for message in messages}))
        self.assertEqual([message["content"] for message in messages], [f"synthetic {index}" for index in range(105)])
        self.assertEqual(self.patient.get(self.url + "/messages", params={"after": messages[-1]["id"]}).json()["messages"], [])
        self.assertEqual(len(self.patient.get(self.url + "/messages?limit=1").json()["messages"]), 1)
        for query in ("limit=0", "limit=101", "limit=bad", "after=-1", "after=bad", "after=9223372036854775808"):
            self.assertEqual(self.patient.get(self.url + "/messages?" + query).status_code, 422)

    def test_strip_validation_extra_fields_and_sender_cannot_be_spoofed(self):
        before = self.snapshot()
        for body in ({}, {"content": ""}, {"content": " \n\t "}, {"content": "x" * 2001}, {"content": 12},
                     {"content": "synthetic", "sender": "doctor"}, {"content": "synthetic", "sender_role": "doctor"},
                     {"content": "synthetic", "request_id": "forged"}):
            response = self.patient.post(self.url + "/messages", json=body)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["error"]["code"], "validation_error")
            self.assertNotIn("synthetic", response.text)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.send(self.patient, " " * 1000 + "x" * 2000 + " " * 1000).status_code, 201)

    def test_message_cap_is_atomic(self):
        with closing(db.connect()) as connection, connection:
            connection.executemany("INSERT INTO visit_messages(request_id,sender_role,content,created_at) VALUES (?,'patient','synthetic',?)",
                                   [(self.visit_id, BASE)] * 499)
        barrier = Barrier(2)
        def post(client):
            barrier.wait(timeout=10)
            return self.send(client, "last synthetic message")
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(post, (self.patient, self.doctor)))
        self.assertEqual(sorted(response.status_code for response in responses), [201, 409])
        rejected = next(response for response in responses if response.status_code == 409)
        self.assertEqual(rejected.json()["error"]["code"], "chat_full")
        self.assertEqual(self.send(self.patient, "overflow").json()["error"]["code"], "chat_full")
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM visit_messages").fetchone()[0], 500)

    def test_ending_is_idempotent_keeps_history_and_locks_both_roles(self):
        message = self.send(self.patient, "synthetic history").json()
        self.assertEqual(self.doctor.post(self.url + "/end").json(), {"ended": True})
        before = self.snapshot()
        self.clock.return_value = "2030-01-01T00:05:00.000000+00:00"
        self.assertEqual(self.doctor.post(self.url + "/end").json(), {"ended": True})
        self.assertEqual(self.snapshot(), before)
        for client in (self.patient, self.doctor):
            response = self.send(client, "must not store")
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["error"]["code"], "visit_ended")
            self.assertEqual(client.get(self.url + "/messages").json(), {"messages": [message], "ended": True, "has_more": False})
        self.assertTrue(self.patient.get("/v1/visit-requests").json()[0]["ended"])
        doctor_visit = self.doctor.get("/v1/doctor/requests").json()[0]
        self.assertTrue(doctor_visit["ended"])
        self.assertEqual(doctor_visit["status"], "accepted")

    def test_end_post_race_never_inserts_after_end(self):
        original = datetime.fromisoformat(BASE)
        lock, barrier = Lock(), Barrier(2)
        tick = 0
        def now():
            nonlocal tick
            with lock:
                tick += 1
                return (original + timedelta(microseconds=tick)).isoformat(timespec="microseconds")
        user = accounts.current_user(self.patient.cookies.get("session"))
        doctor = accounts.current_user(self.doctor.cookies.get("session"))
        def action(role):
            barrier.wait(timeout=10)
            try:
                return chats.post_message(self.visit_id, user, "racing synthetic") if role == "post" else chats.end_visit(self.visit_id, doctor)
            except Exception as error:
                return error
        with patch.object(db, "utc_now", side_effect=now), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(action, ("post", "end")))
        self.assertEqual(results[1], {"ended": True})
        if isinstance(results[0], Exception):
            self.assertIsInstance(results[0], ServiceError)
            self.assertEqual((results[0].status_code, results[0].code), (409, "visit_ended"))
        else:
            self.assertEqual(results[0]["sender"], "patient")
        with closing(db.connect()) as connection:
            end = connection.execute("SELECT ended_at FROM visit_requests WHERE id=?", (self.visit_id,)).fetchone()[0]
            rows = connection.execute("SELECT created_at FROM visit_messages WHERE request_id=?", (self.visit_id,)).fetchall()
            self.assertTrue(all(row[0] <= end for row in rows))
        self.assertEqual(self.send(self.doctor, "late message").status_code, 409)

    def test_patient_polling_and_message_reads_change_no_rows(self):
        self.send(self.doctor, "synthetic")
        other_session = self.patient.post("/v1/chat/sessions").json()["session_id"]
        with closing(db.connect()) as connection, connection:
            connection.execute("""INSERT INTO visit_requests(id,patient_id,session_id,specialty_code,status,created_at,updated_at)
                VALUES ('stale-pending',?,?, 'general_practice','pending',?,?)""",
                (self.patient_user["patient_id"], other_session, BASE, BASE))
        self.clock.return_value = "2030-01-01T00:31:00.000000+00:00"
        before = self.snapshot()
        for client in (self.patient, self.doctor):
            self.assertEqual(client.get(self.url + "/messages").status_code, 200)
        items = self.patient.get("/v1/visit-requests").json()
        self.assertEqual(next(item["status"] for item in items if item["id"] == "stale-pending"), "expired")
        self.assertEqual(self.snapshot(), before)

    def test_patient_delete_cascades_messages_and_removes_raw_text(self):
        marker = "synthetic_private_chat_marker"
        self.send(self.patient, marker)
        self.send(self.doctor, marker)
        self.assertEqual(self.patient.delete("/v1/me").status_code, 204)
        after = self.snapshot()
        self.assertEqual(after["visit_messages"], [])
        self.assertEqual(after["visit_requests"], [])
        self.assertNotIn(marker, repr(after))
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA secure_delete").fetchone()[0], 1)

    def test_v5_upgrade_matches_fresh_schema_and_concurrent_connections(self):
        self.send(self.patient, "preserve only pre-chat data")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE visit_messages")
            connection.execute("ALTER TABLE visit_requests DROP COLUMN ended_at")
            connection.execute("PRAGMA user_version=5")
        with ThreadPoolExecutor(max_workers=3) as pool:
            def connect(_):
                with closing(db.connect()) as connection:
                    return connection.execute("PRAGMA user_version").fetchone()[0]
            self.assertEqual(list(pool.map(connect, range(3))), [7, 7, 7])
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT status FROM visit_requests WHERE id=?", (self.visit_id,)).fetchone()[0], "accepted")
            def structure(connection):
                names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
                return {name: {kind: [tuple(row) for row in connection.execute(f'PRAGMA {kind}("{name}")')]
                               for kind in ("table_info", "foreign_key_list", "index_list")} for name in names}
            upgraded = structure(connection)
        fresh = self.path.with_name("fresh.db")
        with patch.dict(os.environ, {"APP_DB_PATH": str(fresh)}), ThreadPoolExecutor(max_workers=3) as pool:
            self.assertEqual(list(pool.map(connect, range(3))), [7, 7, 7])
            with closing(db.connect()) as connection:
                self.assertEqual(structure(connection), upgraded)
                self.assertEqual([row[2] for row in connection.execute("PRAGMA index_info(visit_messages_request_id)")], ["request_id", "id"])

    def test_v6_migration_failure_rolls_back_and_can_retry(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE visit_messages")
            connection.execute("ALTER TABLE visit_requests DROP COLUMN ended_at")
            connection.execute("PRAGMA user_version=5")
        original = sqlite3.connect
        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, *args):
                if sql == "PRAGMA user_version=6":
                    raise sqlite3.OperationalError("synthetic migration failure")
                return super().execute(sql, *args)
        with patch.object(db.sqlite3, "connect", side_effect=lambda *args, **kwargs: original(*args, **kwargs, factory=FailingConnection)):
            with self.assertRaises(sqlite3.OperationalError):
                db.connect()
        with closing(original(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 5)
            self.assertNotIn("ended_at", {row[1] for row in connection.execute("PRAGMA table_info(visit_requests)")})
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='visit_messages'").fetchone())
        self.assertEqual(self.patient.get(self.url + "/messages").status_code, 200)
