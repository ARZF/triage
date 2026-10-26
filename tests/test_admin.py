import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core import db, security
from app.core.config import Settings
from app.main import app
from app.services import admin, doctors
from helpers import PASSWORD, admin_account, approve_doctor, intake_answers, register_doctor, register_patient

BASE = "2030-01-01T00:00:00.000000+00:00"


class AdminConfigTests(unittest.TestCase):
    def test_config_pair_bounds_and_secret_repr(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(Settings().admin_username)
            for values, expected in (({"admin_username": "admin_demo"}, "APP_ADMIN_USERNAME and APP_ADMIN_PASSWORD"),
                                     ({"admin_password": PASSWORD}, "APP_ADMIN_USERNAME and APP_ADMIN_PASSWORD"),
                                     ({"admin_username": "Admin", "admin_password": PASSWORD}, "APP_ADMIN_USERNAME"),
                                     ({"admin_username": "admin_demo", "admin_password": "short"}, "APP_ADMIN_PASSWORD"),
                                     ({"admin_username": "admin_demo", "admin_password": "x" * 129}, "APP_ADMIN_PASSWORD")):
                with self.subTest(values=list(values)), self.assertRaises(ValueError) as error:
                    Settings(**values)
                self.assertEqual(str(error.exception), expected)
            for length in (12, 128):
                settings = Settings(admin_username="admin_demo", admin_password="x" * length)
                self.assertNotIn("admin_demo", repr(settings))
                self.assertNotIn("x" * length, repr(settings))


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "admin.db"
        self.enterContext(patch.dict(os.environ, {"APP_DB_PATH": str(self.path), "APP_ADMIN_USERNAME": "", "APP_ADMIN_PASSWORD": "",
            "APP_DOCTOR_AUTO_VERIFY": "false", "APP_DEMO_DOCTOR_PASSWORD": "", "APP_LLM_BASE_URL": "", "APP_LLM_MODEL": ""}))
        self.clock = self.enterContext(patch.object(db, "utc_now", return_value=BASE))
        self.client = self.enterContext(TestClient(app))
        self.patient = TestClient(app); self.addCleanup(self.patient.close)
        self.patient_user = register_patient(self.patient)
        self.doctor = TestClient(app); self.addCleanup(self.doctor.close)
        self.doctor_row = register_doctor(self.doctor)
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0], 0)
        self.admin_user = self.enterContext(admin_account(self.client))

    def transition(self, action, note="synthetic review note", doctor_id=None):
        return self.client.post(f"/v1/admin/doctors/{doctor_id or self.doctor_row['id']}/{action}",
                                **({} if action == "approve" else {"json": {"note": note}}))

    def test_registration_license_validation_uniqueness_and_reserved_names(self):
        body = {"role": "doctor", "username": "new_doctor", "password": PASSWORD, "name_fa": "پزشک ساختگی",
                "specialty_code": "general_practice", "expertise": ["حوزه اول", "حوزه دوم"], "license_number": " DEMO-NEW "}
        for license in (None, "", "abc", "x" * 21, "bad value", "۱۲۳۴", "x\n123"):
            invalid = {**body, "license_number": license}
            if license is None: invalid.pop("license_number")
            self.assertEqual(self.patient.post("/v1/auth/register", json=invalid).status_code, 422)
        for key in ("status", "review_status", "verified"):
            self.assertEqual(self.patient.post("/v1/auth/register", json={**body, key: "approved"}).status_code, 422)
        self.assertEqual(self.patient.post("/v1/auth/register", json={**body, "role": "admin"}).status_code, 422)
        for name in ("admin", "ADMIN", "admin_demo", "demo_doctor_1"):
            response = self.patient.post("/v1/auth/register", json={**body, "username": name})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["error"]["code"], "username_unavailable")
        response = self.patient.post("/v1/auth/register", json=body)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user"]["doctor"]["status"], "pending")
        self.assertFalse(response.json()["user"]["doctor"]["verified"])
        duplicate = self.patient.post("/v1/auth/register", json={**body, "username": "another_doctor"})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["error"]["code"], "license_unavailable")
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT license_number FROM doctors WHERE license_number='DEMO-NEW'").fetchone()[0], "DEMO-NEW")
            self.assertIsNone(connection.execute("SELECT 1 FROM users WHERE username='another_doctor'").fetchone())
        with patch.dict(os.environ, {"APP_DOCTOR_AUTO_VERIFY": "true"}):
            row = register_doctor(self.patient)
        self.assertEqual((row["review_status"], row["verified"]), ("approved", 1))

    def test_admin_identity_authorization_pages_and_no_store(self):
        self.assertEqual(self.client.get("/v1/auth/me").json()["user"], self.admin_user)
        self.assertEqual((self.admin_user["role"], self.admin_user["display_name"], self.admin_user["doctor"]), ("admin", "مدیر سیستم", None))
        anonymous = TestClient(app); self.addCleanup(anonymous.close)
        for client, status in ((anonymous, 401), (self.patient, 403), (self.doctor, 403)):
            for method, path, body in (("get", "/v1/admin/doctors", None), ("get", "/v1/admin/audit", None),
                                      ("post", "/v1/admin/doctors/unknown/approve", None),
                                      ("post", "/v1/admin/doctors/unknown/reject", {"note": "synthetic"}),
                                      ("post", "/v1/admin/doctors/unknown/suspend", {"note": "synthetic"})):
                response = getattr(client, method)(path, **({"json": body} if body else {}))
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.headers["cache-control"], "no-store")
        for method, path, body in (("post", "/v1/chat/sessions", None), ("get", "/v1/me/history", None), ("delete", "/v1/me", None),
                                  ("get", "/v1/visit-requests", None), ("post", "/v1/visit-requests", {"session_id": "unknown"}),
                                  ("post", "/v1/visit-requests/unknown/cancel", None), ("get", "/v1/doctor/requests", None),
                                  ("put", "/v1/doctor/availability", {"available": True}), ("post", "/v1/doctor/requests/unknown/accept", None),
                                  ("post", "/v1/chat/sessions/unknown/messages", {"message": "synthetic"}), ("post", "/v1/chat/sessions/unknown/triage", None),
                                  ("get", "/v1/visit-requests/unknown/messages", None), ("post", "/v1/visit-requests/unknown/messages", {"content": "synthetic"}),
                                  ("post", "/v1/visit-requests/unknown/end", None)):
            response = getattr(self.client, method)(path, **({"json": body} if body else {}))
            self.assertEqual(response.status_code, 403, path)
            self.assertEqual(response.headers["cache-control"], "no-store")
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn('lang="fa" dir="rtl"', response.text)
        self.assertNotIn("innerHTML", response.text)
        self.assertIn('<script src="/assets/shell.js">', response.text)
        self.assertIn('href="/assets/shell.css"', response.text)

    def test_list_projection_paging_order_and_validation(self):
        self.clock.return_value = "2030-01-01T00:01:00.000000+00:00"
        second = register_doctor(self.patient)
        response = self.client.get("/v1/admin/doctors?limit=1")
        self.assertEqual(response.headers["cache-control"], "no-store")
        page = response.json(); self.assertEqual(page["total"], 2)
        self.assertEqual(page["items"][0]["id"], self.doctor_row["id"])
        self.assertEqual(self.client.get("/v1/admin/doctors?limit=1&offset=1").json()["items"][0]["id"], second["id"])
        self.assertEqual(set(page["items"][0]), {"id", "name_fa", "specialty", "expertise", "license_number", "registered_at", "status", "reviewed_at", "review_note", "resubmitted_at"})
        for forbidden in (self.patient_user["id"], self.patient_user["patient_id"], self.patient_user["username"], self.doctor_row["user_id"], "username", "password"):
            self.assertNotIn(forbidden, response.text)
        for query in ("status=bad", "limit=0", "limit=101", "limit=bad", "offset=-1", "offset=9223372036854775808"):
            self.assertEqual(self.client.get("/v1/admin/doctors?"+query).status_code, 422)
        self.transition("approve")
        self.clock.return_value = "2030-01-01T00:02:00.000000+00:00"
        approve_doctor(self.client, second["id"])
        self.assertEqual([row["id"] for row in self.client.get("/v1/admin/doctors?status=approved").json()["items"][:2]], [second["id"], self.doctor_row["id"]])

    def test_every_transition_and_own_review_note(self):
        self.assertEqual(self.transition("suspend").status_code, 409)
        rejected = self.transition("reject", "  synthetic rejection  ")
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["review_note"], "synthetic rejection")
        self.assertEqual(self.transition("reject").status_code, 409)
        self.assertEqual(self.transition("suspend").status_code, 409)
        self.assertEqual(self.doctor.get("/v1/auth/me").json()["user"]["doctor"]["status"], "rejected")
        approved = self.transition("approve")
        self.assertEqual(approved.status_code, 200)
        self.assertIsNone(approved.json()["review_note"])
        self.assertEqual(self.doctor.get("/v1/doctor/requests").status_code, 200)
        self.assertEqual(self.transition("approve").status_code, 409)
        self.assertEqual(self.transition("reject").status_code, 409)
        self.assertEqual(self.transition("suspend").status_code, 200)
        self.assertEqual(self.transition("suspend").status_code, 409)
        self.assertEqual(self.transition("reject").status_code, 409)
        own = self.doctor.get("/v1/auth/me").json()["user"]["doctor"]
        self.assertEqual((own["status"], own["review_note"], own["verified"], own["available"]), ("suspended", "synthetic review note", False, False))
        self.assertEqual(self.doctor.get("/v1/doctor/requests").status_code, 403)
        self.assertEqual(self.transition("approve").status_code, 200)
        self.assertTrue(self.doctor.get("/v1/auth/me").json()["user"]["doctor"]["verified"])
        self.assertFalse(self.doctor.get("/v1/auth/me").json()["user"]["doctor"]["available"])
        for action in ("approve", "reject", "suspend"):
            self.assertEqual(self.transition(action, doctor_id="unknown").status_code, 404)

    def test_required_notes_are_stripped_and_bounded_without_changes(self):
        for action in ("reject", "suspend"):
            for body in ({}, {"note": ""}, {"note": " \n "}, {"note": "ab"}, {"note": "x" * 301}, {"note": 12}, {"note": "synthetic", "verified": True}):
                response = self.client.post(f"/v1/admin/doctors/{self.doctor_row['id']}/{action}", json=body)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("synthetic", response.text)
        self.assertEqual(self.client.get("/v1/admin/audit").json(), {"items": []})
        self.assertEqual(self.transition("reject", " " * 10 + "x" * 300 + " " * 10).status_code, 200)

    def test_pending_approval_and_concurrent_approval_write_one_audit(self):
        barrier = Barrier(2)
        def approve(_):
            barrier.wait(timeout=10)
            return self.transition("approve")
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(approve, range(2)))
        self.assertEqual(sorted(response.status_code for response in responses), [200, 409])
        self.assertEqual(next(response for response in responses if response.status_code == 409).json()["error"]["code"], "invalid_transition")
        audit = self.client.get("/v1/admin/audit").json()["items"]
        self.assertEqual(len(audit), 1)
        self.assertEqual((audit[0]["action"], audit[0]["from_status"], audit[0]["to_status"], audit[0]["note"]), ("approve", "pending", "approved", None))
        self.assertEqual(self.doctor.get("/v1/doctor/requests").status_code, 200)

    def visit(self, client):
        client.post("/v1/doctor/heartbeat")
        state = self.patient.post("/v1/chat/sessions").json()
        path = f"/v1/chat/sessions/{state['session_id']}/messages"
        if state["step"] == "profile": self.patient.post(path, json={"message": "no"})
        for answer in intake_answers(): self.assertEqual(self.patient.post(path, json={"message": answer}).status_code, 200)
        self.patient.post(f"/v1/chat/sessions/{state['session_id']}/triage")
        visit = self.patient.post("/v1/visit-requests", json={"session_id": state["session_id"]}).json()
        self.assertEqual(client.post(f"/v1/doctor/requests/{visit['id']}/accept").status_code, 200)
        return visit["id"]

    def test_suspension_ends_only_own_open_visits_and_reinstatement_keeps_history(self):
        approve_doctor(self.client, self.doctor_row["id"])
        visit = self.visit(self.doctor)
        self.patient.post(f"/v1/visit-requests/{visit}/messages", json={"content": "synthetic retained history"})
        other = TestClient(app); self.addCleanup(other.close)
        other_doctor = register_doctor(other); approve_doctor(self.client, other_doctor["id"])
        other_visit = self.visit(other)
        self.clock.return_value = "2030-01-01T00:01:00.000000+00:00"
        with self.assertNoLogs("app", level="DEBUG"):
            self.assertEqual(self.transition("suspend", "synthetic suspension").status_code, 200)
        listed = {row["id"]: row for row in self.patient.get("/v1/visit-requests").json()}
        self.assertTrue(listed[visit]["ended"]); self.assertFalse(listed[other_visit]["ended"])
        history = self.patient.get(f"/v1/visit-requests/{visit}/messages").json()
        self.assertTrue(history["ended"]); self.assertEqual(history["messages"][0]["content"], "synthetic retained history")
        self.assertEqual(self.patient.post(f"/v1/visit-requests/{visit}/messages", json={"content": "late"}).json()["error"]["code"], "visit_ended")
        self.assertEqual(self.doctor.get("/v1/doctor/requests").status_code, 403)
        self.assertNotIn(self.doctor_row["id"], [row["id"] for row in doctors.for_specialty("general_practice")])
        with closing(db.connect()) as connection:
            row = connection.execute("SELECT * FROM doctors WHERE id=?", (self.doctor_row["id"],)).fetchone()
            self.assertIsNone(row["last_seen_at"]); self.assertEqual((row["verified"], row["available"]), (0, 0))
            self.assertEqual(connection.execute("SELECT ended_at FROM visit_requests WHERE id=?", (visit,)).fetchone()[0], self.clock.return_value)
        approve_doctor(self.client, self.doctor_row["id"])
        self.assertTrue(self.doctor.get(f"/v1/visit-requests/{visit}/messages").json()["ended"])

    def test_rejection_denies_data_but_allows_login_and_audit_is_ordered_and_bounded(self):
        self.transition("reject", "synthetic rejection")
        self.assertEqual(self.doctor.post("/v1/auth/login", json={"username": self.doctor.get("/v1/auth/me").json()["user"]["username"], "password": PASSWORD}).status_code, 200)
        self.assertEqual(self.doctor.get("/v1/doctor/requests").status_code, 403)
        self.assertNotIn(self.doctor_row["id"], [row["id"] for row in doctors.for_specialty("general_practice")])
        self.clock.return_value = "2030-01-01T00:01:00.000000+00:00"; self.transition("approve")
        response = self.client.get("/v1/admin/audit?limit=1")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual([row["action"] for row in response.json()["items"]], ["approve"])
        all_rows = self.client.get("/v1/admin/audit").json()["items"]
        self.assertEqual([row["action"] for row in all_rows], ["approve", "reject"])
        self.assertEqual(set(all_rows[0]), {"id", "action", "doctor_id", "doctor_name_fa", "from_status", "to_status", "note", "created_at"})
        with closing(db.connect()) as connection, connection:
            connection.execute("INSERT INTO admin_audit(admin_user_id,action,doctor_id,created_at) VALUES (?,'approve','missing',?)", (self.admin_user["id"], self.clock.return_value))
        self.assertIsNone(self.client.get("/v1/admin/audit?limit=1").json()["items"][0]["doctor_name_fa"])
        for limit in (0, 101, "bad"):
            self.assertEqual(self.client.get(f"/v1/admin/audit?limit={limit}").status_code, 422)

    def test_failed_audit_insert_rolls_back_suspension_and_visit_end(self):
        approve_doctor(self.client, self.doctor_row["id"]); visit = self.visit(self.doctor)
        with closing(db.connect()) as connection, connection:
            connection.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON admin_audit BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        self.assertEqual(self.transition("suspend").status_code, 500)
        self.assertTrue(self.doctor.get("/v1/auth/me").json()["user"]["doctor"]["verified"])
        self.assertFalse(next(row for row in self.patient.get("/v1/visit-requests").json() if row["id"] == visit)["ended"])

    def test_seed_doctor_refresh_preserves_admin_suspension(self):
        self.transition("suspend", doctor_id="demo_doctor_1")
        doctors.seed_doctors()
        with closing(db.connect()) as connection:
            row = connection.execute("SELECT * FROM doctors WHERE id='demo_doctor_1'").fetchone()
            self.assertEqual((row["review_status"], row["verified"], row["review_note"]), ("suspended", 0, "synthetic review note"))
            self.assertIsNone(row["license_number"])

    def test_admin_seeding_disabled_refresh_collision_and_login_throttle(self):
        with patch.dict(os.environ, {"APP_ADMIN_USERNAME": "", "APP_ADMIN_PASSWORD": ""}), self.assertLogs("app.services.admin", level="INFO") as logs:
            admin.seed_admin()
            self.assertEqual(self.client.get("/v1/auth/me").status_code, 401)
        self.assertEqual(logs.output, ["INFO:app.services.admin:admin_disabled"])
        with closing(db.connect()) as connection:
            before = dict(connection.execute("SELECT * FROM users WHERE role='admin'").fetchone())
        new_password = "synthetic-refreshed-password"
        with patch.dict(os.environ, {"APP_ADMIN_PASSWORD": new_password}):
            with TestClient(app) as restarted:
                self.assertEqual(restarted.post("/v1/auth/login", json={"username": "admin_demo", "password": new_password}).status_code, 200)
        with closing(db.connect()) as connection:
            after = dict(connection.execute("SELECT * FROM users WHERE role='admin'").fetchone())
        self.assertEqual(after["id"], before["id"]); self.assertNotEqual(after["password_hash"], before["password_hash"])
        self.assertNotIn(new_password, repr(after))
        self.assertTrue(security.verify_password(new_password, after["password_hash"]))
        for username in (self.patient_user["username"], self.doctor.get("/v1/auth/me").json()["user"]["username"]):
            with patch.dict(os.environ, {"APP_ADMIN_USERNAME": username}), self.assertRaises(ValueError) as error:
                with TestClient(app): pass
            self.assertEqual(str(error.exception), "APP_ADMIN_USERNAME")
        security.clear_failures("admin_demo")
        for _ in range(5):
            self.assertEqual(self.client.post("/v1/auth/login", json={"username": "admin_demo", "password": "wrong-password"}).status_code, 401)
        self.assertEqual(self.client.post("/v1/auth/login", json={"username": "admin_demo", "password": new_password}).status_code, 429)
        security.clear_failures("admin_demo")


class AdminMigrationTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "migration.db"
        self.enterContext(patch.dict(os.environ, {"APP_DB_PATH": str(self.path), "APP_ADMIN_USERNAME": "", "APP_ADMIN_PASSWORD": "",
            "APP_DOCTOR_AUTO_VERIFY": "true", "APP_DEMO_DOCTOR_PASSWORD": "", "APP_LLM_BASE_URL": "", "APP_LLM_MODEL": ""}))
        self.enterContext(patch.object(db, "utc_now", return_value=BASE))
        self.patient = self.enterContext(TestClient(app)); register_patient(self.patient)
        self.doctor = TestClient(app); self.addCleanup(self.doctor.close)
        self.approved = register_doctor(self.doctor)
        with patch.dict(os.environ, {"APP_DOCTOR_AUTO_VERIFY": "false"}):
            self.pending = register_doctor(self.doctor)
        self.doctor.post("/v1/auth/login", json={"username": self.username(self.approved["user_id"]), "password": PASSWORD})
        self.doctor.post("/v1/doctor/heartbeat")
        state = self.patient.post("/v1/chat/sessions").json()
        for answer in intake_answers(): self.patient.post(f"/v1/chat/sessions/{state['session_id']}/messages", json={"message": answer})
        self.patient.post(f"/v1/chat/sessions/{state['session_id']}/triage")
        self.visit_id = self.patient.post("/v1/visit-requests", json={"session_id": state["session_id"]}).json()["id"]
        self.doctor.post(f"/v1/doctor/requests/{self.visit_id}/accept")
        self.patient.post(f"/v1/visit-requests/{self.visit_id}/messages", json={"content": "synthetic migration history"})
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DROP TABLE admin_audit")
            connection.execute("DROP TABLE patient_profiles")
            connection.execute("DROP INDEX doctors_license_number")
            for name in ("review_status", "license_number", "reviewed_at", "review_note", "resubmitted_at"):
                connection.execute(f"ALTER TABLE doctors DROP COLUMN {name}")
            user_sql = "CREATE TABLE users_v6 (" + db.SCHEMA.split("CREATE TABLE IF NOT EXISTS users (", 1)[1].split(";", 1)[0]
            connection.execute(user_sql)
            connection.execute("INSERT INTO users_v6 SELECT * FROM users")
            connection.execute("DROP TABLE users")
            connection.execute("ALTER TABLE users_v6 RENAME TO users")
            connection.execute("PRAGMA user_version=6")
        self.before = self.rows()

    def username(self, id):
        with closing(db.connect()) as connection:
            return connection.execute("SELECT username FROM users WHERE id=?", (id,)).fetchone()[0]

    def rows(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return {name: connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
                    for name in ("users", "doctors", "patients", "sessions", "auth_sessions", "messages", "triage_results", "visit_requests", "visit_messages")}

    def test_v6_upgrade_preserves_links_data_indexes_and_concurrent_first_connections(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE INDEX user_created_custom ON users(created_at)")
        barrier = Barrier(3)
        def migrate(_):
            barrier.wait(timeout=10)
            with closing(db.connect()) as connection:
                return (connection.execute("PRAGMA user_version").fetchone()[0], connection.execute("PRAGMA foreign_keys").fetchone()[0])
        with ThreadPoolExecutor(max_workers=3) as pool:
            self.assertEqual(list(pool.map(migrate, range(3))), [(8, 1)] * 3)
        after = self.rows()
        for name, rows in self.before.items():
            self.assertEqual([row[:len(rows[0])] for row in after[name]] if rows else after[name], rows, name)
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA secure_delete").fetchone()[0], 1)
            self.assertIsNotNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='user_created_custom'").fetchone())
            for id, expected in ((self.approved["id"], "approved"), (self.pending["id"], "pending")):
                self.assertEqual(connection.execute("SELECT review_status FROM doctors WHERE id=?", (id,)).fetchone()[0], expected)
        self.assertEqual(self.patient.get("/v1/auth/me").status_code, 200)
        self.assertEqual(self.doctor.get("/v1/auth/me").status_code, 200)
        self.assertEqual(self.patient.get(f"/v1/visit-requests/{self.visit_id}/messages").json()["messages"][0]["content"], "synthetic migration history")

    def test_failure_rolls_back_and_restores_foreign_keys_then_retry_succeeds(self):
        original = sqlite3.connect; closed_flags = []
        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, *args):
                if sql == "PRAGMA user_version=7": raise sqlite3.OperationalError("synthetic migration failure")
                return super().execute(sql, *args)
            def close(self):
                closed_flags.append(super().execute("PRAGMA foreign_keys").fetchone()[0]); super().close()
        with patch.object(db.sqlite3, "connect", side_effect=lambda *args, **kwargs: original(*args, **kwargs, factory=FailingConnection)):
            with self.assertRaises(sqlite3.OperationalError): db.connect()
        self.assertEqual(closed_flags, [1]); self.assertEqual(self.rows(), self.before)
        with closing(original(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 6)
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='admin_audit'").fetchone())
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 8)

    def test_foreign_key_check_aborts_rebuild_without_changing_old_schema(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE doctors SET user_id='missing-user' WHERE id=?", (self.pending["id"],))
        with self.assertRaises(sqlite3.IntegrityError): db.connect()
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 6)
            self.assertNotIn("review_status", {row[1] for row in connection.execute("PRAGMA table_info(doctors)")})
            self.assertNotIn("'admin'", connection.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()[0])

    def test_fresh_and_upgraded_schema_match_and_connect_twice_is_safe(self):
        def structure(connection):
            names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            return {name: {kind: [tuple(row) for row in connection.execute(f'PRAGMA {kind}("{name}")')]
                           for kind in ("table_info", "foreign_key_list", "index_list")} for name in names}
        with closing(db.connect()) as connection: upgraded = structure(connection)
        with closing(db.connect()) as connection: self.assertEqual(structure(connection), upgraded)
        with patch.dict(os.environ, {"APP_DB_PATH": str(self.path.with_name("fresh.db"))}):
            barrier = Barrier(3)
            def connect(_):
                barrier.wait(timeout=10)
                with closing(db.connect()) as connection: return connection.execute("PRAGMA user_version").fetchone()[0]
            with ThreadPoolExecutor(max_workers=3) as pool: self.assertEqual(list(pool.map(connect, range(3))), [8, 8, 8])
            with closing(db.connect()) as connection:
                self.assertEqual(structure(connection), upgraded)
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
