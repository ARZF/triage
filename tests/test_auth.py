import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core import db, security
from app.core.config import Settings
from app.main import app
from app.services import doctors
from helpers import PASSWORD, register_doctor, register_patient

BASE = "2030-01-01T00:00:00.000000+00:00"


class SecurityTests(unittest.TestCase):
    def test_scrypt_round_trip_unique_salts_and_malformed_hashes(self):
        first = security.hash_password(PASSWORD)
        second = security.hash_password(PASSWORD)
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("scrypt$16384$8$1$"))
        self.assertTrue(security.verify_password(PASSWORD, first))
        self.assertFalse(security.verify_password("wrong-password", first))
        for value in ("invalid", first.replace("$16384$", "$1073741824$"), first[:-8]):
            self.assertFalse(security.verify_password(PASSWORD, value))

    def test_auth_config_bounds_and_secret_repr(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            self.assertFalse(settings.cookie_secure)
            self.assertFalse(settings.doctor_auto_verify)
            self.assertEqual(settings.session_ttl_hours, 12)
            self.assertEqual(settings.request_ttl_minutes, 30)
            self.assertNotIn("synthetic-seed-password", repr(Settings(demo_doctor_password="synthetic-seed-password")))
        invalid = {
            "APP_COOKIE_SECURE": ["yes", "1", ""], "APP_DOCTOR_AUTO_VERIFY": ["yes", "0", ""],
            "APP_SESSION_TTL_HOURS": ["0", "169", "1.5", "invalid"],
            "APP_REQUEST_TTL_MINUTES": ["0", "1441", "invalid"],
            "APP_DEMO_DOCTOR_PASSWORD": ["short", "x" * 129],
        }
        for name, values in invalid.items():
            for value in values:
                with self.subTest(name=name, value_length=len(value)), patch.dict(os.environ, {name: value}):
                    with self.assertRaises(ValueError) as error:
                        Settings()
                    self.assertEqual(str(error.exception), name)
        for name, values in (("APP_SESSION_TTL_HOURS", ("1", "168")), ("APP_REQUEST_TTL_MINUTES", ("1", "1440"))):
            for value in values:
                with patch.dict(os.environ, {name: value}):
                    Settings()

    def test_throttle_storage_is_bounded(self):
        with security.FAILURE_LOCK:
            security.FAILURES.clear()
        self.addCleanup(security.FAILURES.clear)
        with patch.object(db, "utc_now", return_value=BASE):
            for index in range(10001):
                security.record_failure(str(index))
        self.assertEqual(len(security.FAILURES), 10000)
        self.assertNotIn("0", security.FAILURES)


class AuthTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.db_path = Path(directory) / "auth.db"
        self.enterContext(patch.dict(os.environ, {
            "APP_DB_PATH": str(self.db_path), "APP_COOKIE_SECURE": "false",
            "APP_SESSION_TTL_HOURS": "12", "APP_DEMO_DOCTOR_PASSWORD": "",
            "APP_DOCTOR_AUTO_VERIFY": "false", "APP_REQUEST_TTL_MINUTES": "30",
            "APP_LLM_BASE_URL": "", "APP_LLM_MODEL": "",
        }))
        self.clock = self.enterContext(patch.object(db, "utc_now", return_value=BASE))
        with security.FAILURE_LOCK:
            security.FAILURES.clear()
        self.client = self.enterContext(TestClient(app))

    def test_patient_register_cookie_me_logout_and_login(self):
        response = self.client.post("/v1/auth/register", json={"role": "patient", "username": "Synthetic.Patient", "password": PASSWORD})
        self.assertEqual(response.status_code, 201)
        user = response.json()["user"]
        self.assertEqual(user["username"], "synthetic.patient")
        self.assertEqual(user["role"], "patient")
        self.assertIsNone(user["doctor"])
        cookie = response.headers["set-cookie"].lower()
        for flag in ("httponly", "samesite=lax", "path=/", "max-age=43200"):
            self.assertIn(flag, cookie)
        self.assertNotIn("; secure", cookie)
        raw = self.client.cookies.get("session")
        with closing(db.connect()) as connection:
            row = connection.execute("SELECT * FROM auth_sessions").fetchone()
            self.assertEqual(row["token_hash"], security.token_hash(raw))
            for table in ("patients", "users", "doctors", "auth_sessions", "sessions", "messages", "triage_results", "visit_requests"):
                for entry in connection.execute(f"SELECT * FROM {table}"):
                    self.assertNotIn(raw, repr(tuple(entry)))
        self.assertEqual(self.client.get("/v1/auth/me").json()["user"], user)
        old = raw
        self.assertEqual(self.client.post("/v1/auth/logout").status_code, 204)
        self.assertEqual(self.client.get("/v1/auth/me").status_code, 401)
        with closing(db.connect()) as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM auth_sessions WHERE token_hash=?", (security.token_hash(old),)).fetchone())
        response = self.client.post("/v1/auth/login", json={"username": "SYNTHETIC.PATIENT", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(self.client.cookies.get("session"), old)

    def test_cookie_secure_only_when_configured(self):
        with patch.dict(os.environ, {"APP_COOKIE_SECURE": "true", "APP_SESSION_TTL_HOURS": "1"}):
            client = self.enterContext(TestClient(app, base_url="https://testserver"))
            response = client.post("/v1/auth/register", json={"role": "patient", "username": "secure_patient", "password": PASSWORD})
            self.assertEqual(response.status_code, 201)
            self.assertIn("; Secure", response.headers["set-cookie"])
            self.assertIn("Max-Age=3600", response.headers["set-cookie"])
            self.assertEqual(client.get("/v1/auth/me").status_code, 200)

    def test_doctor_registration_login_verification_and_forbidden_role(self):
        doctor = register_doctor(self.client)
        me = self.client.get("/v1/auth/me").json()["user"]
        self.assertEqual(me["role"], "doctor")
        self.assertFalse(me["doctor"]["verified"])
        self.assertTrue(me["doctor"]["available"])
        with closing(db.connect()) as connection:
            self.assertIsNone(connection.execute("SELECT score FROM doctors WHERE id=?", (doctor["id"],)).fetchone()[0])
        for method, path, body in (
            ("get", "/v1/doctor/requests", None),
            ("put", "/v1/doctor/availability", {"available": True}),
            ("post", "/v1/doctor/requests/unknown/accept", None),
            ("post", "/v1/chat/sessions", None),
            ("get", "/v1/me/history", None),
            ("delete", "/v1/me", None),
        ):
            response = getattr(self.client, method)(path, **({"json": body} if body is not None else {}))
            self.assertEqual(response.status_code, 403)
        username = me["username"]
        self.client.post("/v1/auth/logout")
        self.assertEqual(self.client.post("/v1/auth/login", json={"username": username, "password": PASSWORD}).status_code, 200)
        self.assertEqual(self.client.get("/v1/doctor/requests").status_code, 403)

    def test_registration_validation_duplicates_reserved_and_extra_fields(self):
        patient = {"role": "patient", "username": "valid_patient", "password": PASSWORD}
        doctor = {**patient, "role": "doctor", "name_fa": "پزشک فرضی", "specialty_code": "general_practice", "expertise": ["مرور اطلاعات", "گفت‌وگوی اولیه"]}
        invalid = [
            {**patient, "username": "a"}, {**patient, "username": "bad name"},
            {**patient, "password": "short"}, {**patient, "password": "x" * 129},
            {**patient, "role": "admin"}, {**doctor, "specialty_code": "unknown"},
            {**doctor, "name_fa": "a"}, {**doctor, "expertise": ["single"]},
            {**doctor, "expertise": ["x", "valid"]}, {**doctor, "expertise": ["a" * 41, "valid"]},
        ]
        for body in (patient, doctor):
            for key in ("score", "verified", "available"):
                invalid.append({**body, key: 1})
        for index, body in enumerate(invalid):
            with self.subTest(index=index):
                response = self.client.post("/v1/auth/register", json=body)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"]["code"], "validation_error")
                self.assertNotIn(PASSWORD, response.text)
        self.assertEqual(self.client.post("/v1/auth/register", json=patient).status_code, 201)
        self.assertEqual(self.client.post("/v1/auth/register", json=patient).status_code, 409)
        for role in ("patient", "doctor"):
            body = patient if role == "patient" else doctor
            self.assertEqual(self.client.post("/v1/auth/register", json={**body, "username": "DEMO_DOCTOR_1"}).status_code, 409)

    def test_unknown_and_wrong_password_identical_with_dummy_verification(self):
        user = register_patient(self.client)
        wrong = self.client.post("/v1/auth/login", json={"username": user["username"], "password": "wrong-password"})
        with patch.object(security, "verify_password", wraps=security.verify_password) as verify:
            unknown = self.client.post("/v1/auth/login", json={"username": "unknown_user", "password": "wrong-password"})
        verify.assert_called_once_with("wrong-password", security.DUMMY_HASH)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong.json(), unknown.json())

    def test_session_expiry(self):
        register_patient(self.client)
        self.clock.return_value = "2030-01-01T12:00:00.000001+00:00"
        response = self.client.get("/v1/auth/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_login_throttle_lowercase_retry_after_expiry_and_success_reset(self):
        user = register_patient(self.client)
        for _ in range(4):
            self.assertEqual(self.client.post("/v1/auth/login", json={"username": user["username"].upper(), "password": "wrong-password"}).status_code, 401)
        self.assertEqual(self.client.post("/v1/auth/login", json={"username": user["username"], "password": PASSWORD}).status_code, 200)
        for _ in range(5):
            self.assertEqual(self.client.post("/v1/auth/login", json={"username": user["username"], "password": "wrong-password"}).status_code, 401)
        response = self.client.post("/v1/auth/login", json={"username": user["username"], "password": PASSWORD})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "900")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.clock.return_value = "2030-01-01T00:15:00.000001+00:00"
        self.assertEqual(self.client.post("/v1/auth/login", json={"username": user["username"], "password": PASSWORD}).status_code, 200)
        self.assertNotIn(user["username"], security.FAILURES)

    def test_seed_doctors_idempotent_accounts_optional_and_presence_offline(self):
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM doctors WHERE verified=1").fetchone()[0], 12)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM doctors WHERE last_seen_at IS NOT NULL").fetchone()[0], 0)
        doctors.seed_doctors()
        with patch.dict(os.environ, {"APP_DEMO_DOCTOR_PASSWORD": "synthetic-seed-password"}):
            doctors.seed_doctors()
            with closing(db.connect()) as connection:
                linked = dict(connection.execute("SELECT id,user_id FROM doctors").fetchall())
            doctors.seed_doctors()
            with closing(db.connect()) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0], 12)
                self.assertEqual(dict(connection.execute("SELECT id,user_id FROM doctors").fetchall()), linked)
            response = self.client.post("/v1/auth/login", json={"username": "demo_doctor_1", "password": "synthetic-seed-password"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.client.get("/v1/doctor/requests").status_code, 200)
        doctors.seed_doctors()
        with closing(db.connect()) as connection:
            self.assertEqual(dict(connection.execute("SELECT id,user_id FROM doctors").fetchall()), linked)
        self.assertEqual(self.client.get("/v1/auth/me").status_code, 401)
        self.assertEqual(self.client.post("/v1/auth/login", json={"username": "demo_doctor_1", "password": "synthetic-seed-password"}).status_code, 401)

    def test_no_cookie_role_boundaries_no_store_pages_and_specialties(self):
        for path, method in (("/v1/auth/logout", "post"), ("/v1/auth/me", "get"), ("/v1/me/history", "get"), ("/v1/chat/sessions", "post"), ("/v1/visit-requests", "get"), ("/v1/doctor/requests", "get")):
            response = getattr(self.client, method)(path)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers["cache-control"], "no-store")
        register_patient(self.client)
        self.assertEqual(self.client.get("/v1/doctor/requests").status_code, 403)
        for path in ("/login", "/doctor", "/demo"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/html", response.headers["content-type"])
            self.assertIn('lang="fa" dir="rtl"', response.text)
            self.assertNotIn("innerHTML", response.text)
            self.assertNotIn("<script src=", response.text)
        response = self.client.get("/v1/specialties")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(len(response.json()), 9)
        self.assertEqual(set(response.json()[0]), {"code", "name_fa"})
        self.assertEqual(self.client.get("/v1/does-not-exist").headers["cache-control"], "no-store")

    def test_auth_actions_log_no_credentials_or_username(self):
        with self.assertNoLogs("app", level="DEBUG"):
            register_patient(self.client)
            self.client.post("/v1/auth/logout")

    def test_database_hardening_skips_schema_writes_on_normal_connections(self):
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)
            self.assertEqual(connection.execute("PRAGMA secure_delete").fetchone()[0], 1)
            connection.execute("BEGIN IMMEDIATE")
            with patch.object(db, "SCHEMA", "invalid schema must not execute"):
                with closing(db.connect()) as reader:
                    self.assertEqual(reader.execute("PRAGMA user_version").fetchone()[0], 3)
            connection.rollback()
