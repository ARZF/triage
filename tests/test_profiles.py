import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agent.context import build_context
from app.agent.intake import PROFILE_FIELDS
from app.core import db, security
from app.main import app
from app.services import accounts, doctors
from helpers import PASSWORD, admin_account, approve_doctor, intake_answers, register_doctor, register_patient

BASE = "2030-01-01T00:00:00.000000+00:00"
FULL = dict(zip(PROFILE_FIELDS, (35, "۱۷۵٫۵", "٧٥.٢", "none", "ibuprofen", "none", "none", "none")))


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "profiles.db"
        self.enterContext(patch.dict(os.environ, {"APP_DB_PATH": str(self.path), "APP_ADMIN_USERNAME": "", "APP_ADMIN_PASSWORD": "",
            "APP_DEMO_DOCTOR_PASSWORD": "", "APP_DOCTOR_AUTO_VERIFY": "false", "APP_LLM_BASE_URL": "", "APP_LLM_MODEL": ""}))
        self.clock = self.enterContext(patch.object(db, "utc_now", return_value=BASE))
        security.FAILURES.clear()
        self.addCleanup(security.FAILURES.clear)
        self.patient = self.enterContext(TestClient(app))
        self.patient_user = register_patient(self.patient)
        self.doctor = TestClient(app); self.addCleanup(self.doctor.close)
        self.doctor_row = register_doctor(self.doctor)
        self.admin = TestClient(app); self.addCleanup(self.admin.close)
        self.enterContext(admin_account(self.admin))

    def snapshot(self):
        with closing(db.connect()) as connection:
            return list(connection.iterdump())

    def row(self, table, id):
        key = "patient_id" if table == "patient_profiles" else "id"
        with closing(db.connect()) as connection:
            row = connection.execute(f"SELECT * FROM {table} WHERE {key}=?", (id,)).fetchone()
            return dict(row) if row else None

    def complete(self, age="30", medications="none"):
        state = self.patient.post("/v1/chat/sessions").json()
        path = f"/v1/chat/sessions/{state['session_id']}/messages"
        if state["step"] == "profile": self.patient.post(path, json={"message": "no"})
        for answer in intake_answers(age=age, medications=medications):
            response = self.patient.post(path, json={"message": answer})
            self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["done"])
        return response.json()

    def accepted_visit(self):
        approve_doctor(self.admin, self.doctor_row["id"])
        self.assertEqual(self.doctor.post("/v1/doctor/heartbeat").status_code, 204)
        state = self.complete()
        self.patient.post(f"/v1/chat/sessions/{state['session_id']}/triage")
        result = self.patient.post("/v1/visit-requests", json={"session_id": state["session_id"]})
        self.assertEqual(result.status_code, 201, result.text)
        id = result.json()["id"]
        self.assertEqual(self.doctor.post(f"/v1/doctor/requests/{id}/accept").status_code, 200)
        return id

    def test_empty_partial_full_profile_and_medication_codes(self):
        response = self.patient.get("/v1/patient/profile")
        self.assertEqual(response.json(), {"profile": dict.fromkeys(PROFILE_FIELDS), "updated_at": None, "complete": False})
        self.assertEqual(response.headers["cache-control"], "no-store")
        partial = self.patient.patch("/v1/patient/profile", json={"age": 0}).json()
        self.assertFalse(partial["complete"])
        self.assertEqual(partial["profile"]["age"], 0)
        self.clock.return_value = "2030-01-01T00:00:01.000000+00:00"
        response = self.patient.patch("/v1/patient/profile", json=FULL)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["complete"])
        self.assertEqual(body["profile"], {**FULL, "height_cm": 175.5, "weight_kg": 75.2})
        self.assertEqual(body["updated_at"], self.clock.return_value)
        self.assertEqual(json.loads(self.row("patient_profiles", self.patient_user["patient_id"])["medication_codes"]), ["ibuprofen"])
        self.patient.patch("/v1/patient/profile", json={"medications": "  هیچ  "})
        self.assertEqual(self.patient.get("/v1/patient/profile").json()["profile"]["medications"], "هیچ")
        self.assertEqual(json.loads(self.row("patient_profiles", self.patient_user["patient_id"])["medication_codes"]), [])

    def test_patient_validation_and_role_isolation(self):
        for body in ({}, {"age": -1}, {"age": 121}, {"age": 1.5}, {"age": True}, {"age": "30"},
                     {"height_cm": 0}, {"weight_kg": "nan"}, {"height_cm": True}, {"height_cm": "1e3"},
                     {"weight_kg": -1}, {"age": None}, {"symptoms": "private-marker"},
                     *({name: value} for name in PROFILE_FIELDS[3:] for value in (" ", "x" * 2001, None, 123))):
            before = self.snapshot()
            response = self.patient.patch("/v1/patient/profile", json=body)
            self.assertEqual(response.status_code, 422, str(list(body)))
            self.assertEqual(self.snapshot(), before)
            self.assertNotIn("private-marker", response.text)
        self.assertEqual(self.patient.patch("/v1/patient/profile", json={"age": 120}).status_code, 200)
        for text in ('{"height_cm":1e309}', '{"weight_kg":' + '9' * 1000 + '}'):
            self.assertEqual(self.patient.patch("/v1/patient/profile", content=text, headers={"Content-Type": "application/json"}).status_code, 422)
        for client in (self.doctor, self.admin):
            for method in ("get", "patch"):
                response = getattr(client, method)("/v1/patient/profile", **({"json": {"age": 40}} if method == "patch" else {}))
                self.assertEqual(response.status_code, 403)
        other = TestClient(app); self.addCleanup(other.close); register_patient(other)
        self.assertFalse(other.get("/v1/patient/profile").json()["complete"])
        other.patch("/v1/patient/profile", json={"age": 10})
        self.assertEqual(self.patient.get("/v1/patient/profile").json()["profile"]["age"], 120)

    def test_edited_profile_prefills_new_intake_without_changing_past_context(self):
        state = self.complete()
        history = self.patient.get("/v1/me/history").json()
        with closing(db.connect()) as connection:
            context = build_context(connection, state["session_id"], for_doctor=True)
        self.clock.return_value = "2030-01-01T00:00:01.000000+00:00"
        self.patient.patch("/v1/patient/profile", json=FULL)
        self.assertEqual(self.patient.get("/v1/me/history").json(), history)
        with closing(db.connect()) as connection:
            self.assertEqual(build_context(connection, state["session_id"], for_doctor=True), context)
        new = self.patient.post("/v1/chat/sessions").json()
        self.assertTrue(new["returning"])
        self.assertEqual(new["step"], "profile")
        self.assertEqual(new["collected"]["age"], 35)
        self.assertIn("۳۵", new["reply"])
        self.assertIn("ibuprofen", new["reply"])
        self.assertEqual(json.loads(self.row("sessions", new["session_id"])["medication_codes"]), ["ibuprofen"])
        self.patient.patch("/v1/patient/profile", json={"age": 40})
        self.assertTrue(self.patient.get(f"/v1/chat/sessions/{new['session_id']}").json()["session"]["returning"])

    def test_profile_only_without_completed_history_is_returning(self):
        self.patient.patch("/v1/patient/profile", json=FULL)
        state = self.patient.post("/v1/chat/sessions").json()
        self.assertEqual(state["step"], "profile")
        self.assertTrue(state["returning"])
        self.patient.post(f"/v1/chat/sessions/{state['session_id']}/messages", json={"message": "no"})
        self.assertTrue(self.patient.get(f"/v1/chat/sessions/{state['session_id']}").json()["session"]["returning"])

    def test_legacy_welcome_remains_returning_after_copy_update(self):
        from app.agent.intake import LEGACY_PROFILE_WELCOME, PROFILE_WELCOME
        self.patient.patch("/v1/patient/profile", json=FULL)
        state = self.patient.post("/v1/chat/sessions").json()
        self.assertTrue(state["reply"].startswith(PROFILE_WELCOME))
        self.assertNotIn("نمایشی", state["reply"])
        with closing(db.connect()) as connection, connection:
            connection.execute("UPDATE messages SET content=? WHERE id=(SELECT MIN(id) FROM messages WHERE session_id=?)",
                               (LEGACY_PROFILE_WELCOME + "اطلاعات نمونه", state["session_id"]))
        restored = self.patient.get(f"/v1/chat/sessions/{state['session_id']}").json()
        self.assertTrue(restored["session"]["returning"])
        self.assertTrue(restored["transcript"][0]["content"].startswith(LEGACY_PROFILE_WELCOME))

    def test_completion_upsert_stale_intake_guard_and_emergency_no_op(self):
        self.complete()
        state = self.patient.post("/v1/chat/sessions").json()
        path = f"/v1/chat/sessions/{state['session_id']}/messages"
        self.patient.post(path, json={"message": "no"})
        self.clock.return_value = "2030-01-01T00:00:01.000000+00:00"
        edited = self.patient.patch("/v1/patient/profile", json={"age": 75, "medications": "ibuprofen"}).json()
        self.clock.return_value = "2030-01-01T00:00:02.000000+00:00"
        for answer in intake_answers(): self.patient.post(path, json={"message": answer})
        self.assertEqual(self.patient.get("/v1/patient/profile").json(), edited)
        emergency = self.patient.post("/v1/chat/sessions").json()
        path = f"/v1/chat/sessions/{emergency['session_id']}/messages"
        self.patient.post(path, json={"message": "no"})
        for answer in ("30", "170", "70", "chest pain"):
            response = self.patient.post(path, json={"message": answer})
        self.assertTrue(response.json()["emergency"])
        self.assertEqual(self.patient.get("/v1/patient/profile").json(), edited)

    def test_partial_profile_does_not_prefill_and_profile_has_no_red_flag_screen(self):
        response = self.patient.patch("/v1/patient/profile", json={"medical_history": "synthetic chest pain"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.patient.post("/v1/chat/sessions").json()["step"], "age")

    def test_delete_cascades_profile_and_raw_text(self):
        marker = "synthetic-profile-private-marker"
        self.patient.patch("/v1/patient/profile", json={**FULL, "medical_history": marker})
        self.assertEqual(self.patient.delete("/v1/me").status_code, 204)
        self.assertIsNone(self.row("patient_profiles", self.patient_user["patient_id"]))
        self.assertNotIn(marker, repr(self.snapshot()))

    def test_heartbeat_only_presence_read_only_requests_and_atomic_sweep(self):
        approve_doctor(self.admin, self.doctor_row["id"])
        self.assertEqual(self.doctor.get("/v1/doctor/requests").status_code, 200)
        self.assertFalse(next(item["online"] for item in doctors.for_specialty("general_practice") if item["id"] == self.doctor_row["id"]))
        self.assertEqual(self.doctor.post("/v1/doctor/heartbeat").status_code, 204)
        state = self.complete()
        self.patient.post(f"/v1/chat/sessions/{state['session_id']}/triage")
        request = self.patient.post("/v1/visit-requests", json={"session_id": state["session_id"]}).json()
        self.clock.return_value = "2030-01-01T00:31:00.000000+00:00"
        before = self.snapshot()
        self.assertEqual(self.doctor.get("/v1/doctor/requests").json(), [])
        self.assertEqual(self.snapshot(), before)
        with closing(db.connect()) as connection, connection:
            connection.execute("CREATE TRIGGER fail_sweep BEFORE UPDATE ON visit_requests BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        self.assertEqual(self.doctor.post("/v1/doctor/heartbeat").status_code, 500)
        self.assertEqual(self.row("doctors", self.doctor_row["id"])["last_seen_at"], BASE)
        with closing(db.connect()) as connection, connection: connection.execute("DROP TRIGGER fail_sweep")
        response = self.doctor.post("/v1/doctor/heartbeat")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.row("visit_requests", request["id"])["status"], "expired")
        self.assertEqual(self.row("doctors", self.doctor_row["id"])["last_seen_at"], self.clock.return_value)

    def test_heartbeat_authorization_and_online_window(self):
        for client in (self.patient, self.admin, self.doctor):
            self.assertEqual(client.post("/v1/doctor/heartbeat").status_code, 403)
        approve_doctor(self.admin, self.doctor_row["id"])
        self.doctor.post("/v1/doctor/heartbeat")
        for seconds, expected in ((89, True), (91, False)):
            self.clock.return_value = f"2030-01-01T00:01:{seconds-60:02}.000000+00:00"
            self.assertEqual(next(item["online"] for item in doctors.for_specialty("general_practice") if item["id"] == self.doctor_row["id"]), expected)

    def test_doctor_pending_free_edit_approval_and_rereview(self):
        response = self.doctor.get("/v1/doctor/profile")
        self.assertEqual(set(response.json()), {"name_fa", "specialty", "expertise", "license_number", "score", "status", "review_note", "resubmitted_at"})
        self.assertIsNone(response.json()["score"])
        self.assertEqual(self.doctor.patch("/v1/doctor/profile", json={"name_fa": "پزشک ساختگی جدید"}).json()["status"], "pending")
        approve_doctor(self.admin, self.doctor_row["id"])
        self.doctor.post("/v1/doctor/heartbeat")
        free = self.doctor.patch("/v1/doctor/profile", json={"name_fa": "پزشک ویرایش شده", "expertise": ["حوزه اول", "حوزه دوم"]})
        self.assertEqual(free.status_code, 200)
        self.assertEqual(free.json()["status"], "approved")
        self.assertEqual(self.doctor.get("/v1/auth/me").json()["user"]["display_name"], "پزشک ویرایش شده")
        same = self.doctor.patch("/v1/doctor/profile", json={"specialty_code": "general_practice", "license_number": self.doctor_row["license_number"]}).json()
        self.assertIsNone(same["resubmitted_at"])
        self.clock.return_value = "2030-01-01T00:00:01.000000+00:00"
        changed = self.doctor.patch("/v1/doctor/profile", json={"specialty_code": "ent"}).json()
        self.assertEqual(changed["status"], "pending")
        self.assertEqual(changed["resubmitted_at"], self.clock.return_value)
        row = self.row("doctors", self.doctor_row["id"])
        self.assertEqual((row["verified"], row["available"], row["last_seen_at"]), (0, 0, None))
        self.assertEqual(self.doctor.get("/v1/doctor/requests").status_code, 403)
        self.assertNotIn(self.doctor_row["id"], [item["id"] for item in doctors.for_specialty("ent")])
        listed = self.admin.get("/v1/admin/doctors").json()["items"][0]
        self.assertEqual(listed["resubmitted_at"], self.clock.return_value)
        approve_doctor(self.admin, self.doctor_row["id"])
        self.assertEqual(self.doctor.get("/v1/doctor/requests").status_code, 200)
        self.assertIn(self.doctor_row["id"], [item["id"] for item in doctors.for_specialty("ent")])

    def test_active_visits_block_identity_edits_atomically_but_auto_verify_allows(self):
        id = self.accepted_visit()
        for changes in ({"specialty_code": "ent"}, {"license_number": "DEMO-CHANGED"}):
            before = self.snapshot()
            response = self.doctor.patch("/v1/doctor/profile", json=changes)
            self.assertEqual((response.status_code, response.json()["error"]["code"]), (409, "active_visits"))
            self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.doctor.patch("/v1/doctor/profile", json={"expertise": ["حوزه جدید", "حوزه دوم"]}).json()["status"], "approved")
        with patch.dict(os.environ, {"APP_DOCTOR_AUTO_VERIFY": "true"}):
            self.assertEqual(self.doctor.patch("/v1/doctor/profile", json={"specialty_code": "ent"}).json()["status"], "approved")
        self.assertEqual(self.doctor.post(f"/v1/visit-requests/{id}/end").status_code, 200)
        response = self.doctor.patch("/v1/doctor/profile", json={"license_number": "DEMO-CHANGED"})
        self.assertEqual(response.json()["status"], "pending")

    def test_rejected_resubmit_noop_pending_and_suspended_lock(self):
        self.admin.post(f"/v1/admin/doctors/{self.doctor_row['id']}/reject", json={"note": "synthetic reason"})
        before = self.row("doctors", self.doctor_row["id"])
        same = self.doctor.patch("/v1/doctor/profile", json={"name_fa": self.doctor_row["name_fa"]}).json()
        self.assertEqual(same["status"], "rejected")
        self.clock.return_value = "2030-01-01T00:00:01.000000+00:00"
        response = self.doctor.patch("/v1/doctor/profile", json={"name_fa": "نام جدید ساختگی"})
        self.assertEqual(response.json()["status"], "pending")
        self.assertIsNone(response.json()["review_note"])
        self.assertEqual(self.row("doctors", self.doctor_row["id"])["reviewed_at"], before["reviewed_at"])
        self.assertEqual(self.doctor.patch("/v1/doctor/profile", json={"specialty_code": "ent"}).json()["status"], "pending")
        approve_doctor(self.admin, self.doctor_row["id"])
        self.admin.post(f"/v1/admin/doctors/{self.doctor_row['id']}/suspend", json={"note": "synthetic reason"})
        before = self.snapshot()
        response = self.doctor.patch("/v1/doctor/profile", json={"name_fa": "تغییر نام"})
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (403, "profile_locked"))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.doctor.get("/v1/doctor/profile").json()["status"], "suspended")
        self.assertEqual(self.doctor.post("/v1/me/password", json={"current_password": PASSWORD, "new_password": "synthetic-new-password"}).status_code, 204)

    def test_rejected_auto_verify_resubmit(self):
        self.admin.post(f"/v1/admin/doctors/{self.doctor_row['id']}/reject", json={"note": "synthetic reason"})
        with patch.dict(os.environ, {"APP_DOCTOR_AUTO_VERIFY": "true"}):
            response = self.doctor.patch("/v1/doctor/profile", json={"name_fa": "پزشک ساختگی جدید"})
        self.assertEqual(response.json()["status"], "approved")
        self.assertEqual(self.row("doctors", self.doctor_row["id"])["verified"], 1)

    def test_doctor_validation_duplicates_and_roles(self):
        for body in ({}, {"name_fa": " "}, {"name_fa": "x" * 61}, {"expertise": ["one"]}, {"expertise": ["x", "valid"]},
                     {"expertise": ["x" * 41, "valid"]}, {"specialty_code": "unknown"}, {"license_number": "۱۲۳۴"},
                     {"name_fa": None}, *({field: True} for field in ("score", "verified", "status", "available", "resubmitted_at"))):
            before = self.snapshot()
            self.assertEqual(self.doctor.patch("/v1/doctor/profile", json=body).status_code, 422)
            self.assertEqual(self.snapshot(), before)
        other = TestClient(app); self.addCleanup(other.close); row = register_doctor(other)
        before = self.snapshot()
        response = self.doctor.patch("/v1/doctor/profile", json={"license_number": row["license_number"]})
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (409, "license_unavailable"))
        self.assertEqual(self.snapshot(), before)
        for client in (self.patient, self.admin):
            self.assertEqual(client.get("/v1/doctor/profile").status_code, 403)
            self.assertEqual(client.patch("/v1/doctor/profile", json={"name_fa": "نام ساختگی"}).status_code, 403)

    def test_password_hash_cookie_other_sessions_and_no_logs(self):
        other = TestClient(app); self.addCleanup(other.close)
        other.post("/v1/auth/login", json={"username": self.patient_user["username"], "password": PASSWORD})
        cookie = self.patient.cookies.get("session")
        before = self.row("users", self.patient_user["id"])["password_hash"]
        with self.assertNoLogs("app", level="DEBUG"):
            response = self.patient.post("/v1/me/password", json={"current_password": PASSWORD, "new_password": "synthetic-new-password"})
        self.assertEqual(response.status_code, 204)
        self.assertNotIn("set-cookie", response.headers)
        self.assertEqual(self.patient.cookies.get("session"), cookie)
        self.assertEqual(self.patient.get("/v1/auth/me").status_code, 200)
        self.assertEqual(other.get("/v1/auth/me").status_code, 401)
        self.assertNotEqual(self.row("users", self.patient_user["id"])["password_hash"], before)
        self.assertEqual(other.post("/v1/auth/login", json={"username": self.patient_user["username"], "password": PASSWORD}).status_code, 401)
        self.assertEqual(other.post("/v1/auth/login", json={"username": self.patient_user["username"], "password": "synthetic-new-password"}).status_code, 200)

    def test_password_validation_throttle_and_independent_login_counter(self):
        for body in ({}, {"current_password": PASSWORD, "new_password": PASSWORD},
                     {"current_password": PASSWORD, "new_password": "short"}, {"current_password": PASSWORD, "new_password": "x" * 129},
                     {"current_password": PASSWORD, "new_password": "valid-password", "username": "forged"}):
            self.assertEqual(self.patient.post("/v1/me/password", json=body).status_code, 422)
        key = "pw:" + self.patient_user["username"]
        for _ in range(4):
            response = self.patient.post("/v1/me/password", json={"current_password": "wrong-password", "new_password": "synthetic-new-password"})
            self.assertEqual((response.status_code, response.json()["error"]["code"]), (401, "invalid_current_password"))
        self.assertEqual(self.patient.post("/v1/me/password", json={"current_password": PASSWORD, "new_password": "x" * 8}).status_code, 204)
        self.assertNotIn(key, security.FAILURES)
        for _ in range(5): self.patient.post("/v1/me/password", json={"current_password": "wrong-password", "new_password": "synthetic-new-password"})
        response = self.patient.post("/v1/me/password", json={"current_password": "x" * 8, "new_password": "synthetic-new-password"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "900")
        self.assertNotIn(self.patient_user["username"], security.FAILURES)
        self.clock.return_value = "2030-01-01T00:15:00.000001+00:00"
        self.assertEqual(self.patient.post("/v1/me/password", json={"current_password": "x" * 8, "new_password": "x" * 128}).status_code, 204)

    def test_managed_admin_and_seed_passwords(self):
        body = {"current_password": PASSWORD, "new_password": "synthetic-new-password"}
        response = self.admin.post("/v1/me/password", json=body)
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (409, "password_managed"))
        self.assertIn("server configuration", response.json()["error"]["message"])
        with patch.dict(os.environ, {"APP_DEMO_DOCTOR_PASSWORD": PASSWORD}):
            doctors.seed_doctors()
            self.doctor.post("/v1/auth/login", json={"username": "demo_doctor_1", "password": PASSWORD})
            self.assertEqual(self.doctor.post("/v1/me/password", json=body).json()["error"]["code"], "password_managed")

    def test_linked_seed_profile_edits_survive_seed_refresh(self):
        with patch.dict(os.environ, {"APP_DEMO_DOCTOR_PASSWORD": PASSWORD}):
            doctors.seed_doctors()
            self.doctor.post("/v1/auth/login", json={"username": "demo_doctor_1", "password": PASSWORD})
            response = self.doctor.patch("/v1/doctor/profile", json={"name_fa": "نام ساختگی جدید",
                "specialty_code": "ent", "expertise": ["حوزه اول", "حوزه دوم"], "license_number": "DEMO-SEED-EDIT"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "pending")
            doctors.seed_doctors()
            self.assertEqual(self.doctor.get("/v1/doctor/profile").json(), response.json())

    def test_password_failure_rolls_back_hash_and_sessions(self):
        with closing(db.connect()) as connection, connection:
            connection.execute("CREATE TRIGGER fail_revocation BEFORE DELETE ON auth_sessions BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        other = TestClient(app); self.addCleanup(other.close)
        other.post("/v1/auth/login", json={"username": self.patient_user["username"], "password": PASSWORD})
        before = self.snapshot()
        response = self.patient.post("/v1/me/password", json={"current_password": PASSWORD, "new_password": "synthetic-new-password"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.snapshot(), before)

    def test_password_change_during_login_does_not_issue_an_old_password_session(self):
        original = security.verify_password
        replacement = security.hash_password("synthetic-replacement-password")
        def verify(password, encoded):
            valid = original(password, encoded)
            with closing(db.connect()) as connection, connection:
                connection.execute("UPDATE users SET password_hash=? WHERE id=?", (replacement, self.patient_user["id"]))
            return valid
        with closing(db.connect()) as connection:
            count = connection.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0]
        with patch.object(security, "verify_password", side_effect=verify):
            response = self.patient.post("/v1/auth/login", json={"username": self.patient_user["username"], "password": PASSWORD})
        self.assertEqual(response.status_code, 401)
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0], count)

    def downgrade_to_seven(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE patient_profiles")
            connection.execute("ALTER TABLE doctors DROP COLUMN resubmitted_at")
            connection.execute("PRAGMA user_version=7")

    def test_v8_backfill_latest_complete_skip_incomplete_and_concurrent_upgrade(self):
        first = self.complete(medications="ibuprofen")
        self.clock.return_value = "2030-01-01T00:00:01.000000+00:00"
        latest = self.complete(age="40", medications="paracetamol")
        self.clock.return_value = "2030-01-01T00:00:02.000000+00:00"
        emergency = self.complete(age="50")
        with closing(db.connect()) as connection, connection:
            connection.execute("UPDATE sessions SET emergency=1 WHERE id=?", (emergency["session_id"],))
        self.clock.return_value = "2030-01-01T00:00:03.000000+00:00"
        invalid = self.patient.post("/v1/chat/sessions").json()
        with closing(db.connect()) as connection, connection:
            connection.execute("UPDATE sessions SET done=1,age=NULL WHERE id=?", (invalid["session_id"],))
        other = TestClient(app); self.addCleanup(other.close); user = register_patient(other)
        other.post("/v1/chat/sessions")
        self.downgrade_to_seven()
        with ThreadPoolExecutor(max_workers=3) as pool:
            def connect(_):
                with closing(db.connect()) as connection: return connection.execute("PRAGMA user_version").fetchone()[0]
            self.assertEqual(list(pool.map(connect, range(3))), [8, 8, 8])
        row = self.row("patient_profiles", self.patient_user["patient_id"])
        self.assertEqual(row["age"], 40)
        self.assertEqual(json.loads(row["medication_codes"]), ["acetaminophen"])
        self.assertIsNone(self.row("patient_profiles", user["patient_id"]))
        self.assertEqual(self.row("sessions", first["session_id"])["age"], 30)
        self.assertEqual(self.row("sessions", latest["session_id"])["age"], 40)
        self.patient.patch("/v1/patient/profile", json={"age": 50})
        self.assertEqual(self.patient.get("/v1/patient/profile").json()["profile"]["age"], 50)

    def test_v8_migration_failure_rollback_retry_and_schema_equivalence(self):
        self.complete()
        self.downgrade_to_seven()
        original = sqlite3.connect
        class Failing(sqlite3.Connection):
            def execute(self, sql, *args):
                if sql == "PRAGMA user_version=8": raise sqlite3.OperationalError("synthetic migration failure")
                return super().execute(sql, *args)
        with patch.object(db.sqlite3, "connect", side_effect=lambda *args, **kwargs: original(*args, **kwargs, factory=Failing)):
            with self.assertRaises(sqlite3.OperationalError): db.connect()
        with closing(original(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 7)
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='patient_profiles'").fetchone())
            self.assertNotIn("resubmitted_at", {row[1] for row in connection.execute("PRAGMA table_info(doctors)")})
        def structure(connection):
            names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            return {name: {kind: [tuple(row) for row in connection.execute(f'PRAGMA {kind}("{name}")')]
                           for kind in ("table_info", "foreign_key_list", "index_list")} for name in names}
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 8)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA secure_delete").fetchone()[0], 1)
            upgraded = structure(connection)
        with patch.dict(os.environ, {"APP_DB_PATH": str(self.path.with_name("fresh.db"))}):
            with ThreadPoolExecutor(max_workers=3) as pool:
                def connect(_):
                    with closing(db.connect()) as connection: return structure(connection)
                self.assertTrue(all(item == upgraded for item in pool.map(connect, range(3))))

    def test_profile_routes_and_heartbeat_static_contracts(self):
        static = Path(__file__).parents[1] / "src/app/static"
        patient = (static / "index.html").read_text(encoding="utf-8")
        doctor = (static / "doctor.html").read_text(encoding="utf-8")
        self.assertIn('["#/new","#/profile"].includes(hash)', patient)
        self.assertIn('hash==="#/profile"||', doctor)
        self.assertIn('setInterval(heartbeat,20000)', doctor)
        self.assertIn('setInterval(refreshIdentity,15000)', doctor)
        heartbeat = doctor.split('async function heartbeat(){', 1)[1].split('\n}', 1)[0]
        self.assertNotIn('document.hidden', heartbeat)
        self.assertIn('id="doctor-profile-view"', doctor)
        self.assertIn('id="profile-view"', patient)
        sidebar = patient.split('<aside id="shell-sidebar">', 1)[1].split('</aside>', 1)[0]
        self.assertNotIn('delete-account', sidebar)
        for path in [*static.glob("*.html"), *static.glob("*.js")]:
            for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
                self.assertNotIn(sink, path.read_text(encoding="utf-8"))
        for path in ("/demo", "/doctor", "/admin"):
            response = self.patient.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.headers["content-type"].startswith("text/html"))
