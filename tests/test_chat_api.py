from unittest.mock import patch
from pathlib import Path
import tempfile
import os
import unittest
from uuid import UUID

from fastapi.testclient import TestClient

from contextlib import closing

from app.core.db import connect
from app.main import app
from helpers import as_patient, patient_of, register_patient
from app.schemas.common import ErrorResponse


class ChatApiTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "test.db"
        self.enterContext(patch.dict(os.environ, {"APP_DB_PATH": str(self.db_path)}))
        self.client = self.enterContext(TestClient(app))
        self.user = register_patient(self.client)

    def stored_session(self, session_id):
        with closing(connect()) as connection:
            return connection.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()

    def create(self):
        response = self.client.post("/v1/chat/sessions")
        self.assertEqual(response.status_code, 201)
        return response.json()

    def message(self, session_id, message):
        return self.client.post(
            f"/v1/chat/sessions/{session_id}/messages", json={"message": message}
        )

    def test_create_session(self):
        state = self.create()
        self.assertEqual(UUID(hex=state["session_id"]).version, 4)
        self.assertEqual(len(state["session_id"]), 32)
        self.assertEqual(state["step"], "age")
        self.assertFalse(state["done"])
        self.assertFalse(state["emergency"])
        self.assertIn("داده‌های ساختگی", state["reply"])
        self.assertEqual(state["collected"], dict.fromkeys(
            ("age", "symptoms", "duration", "severity", "medications", "allergies")
        ))

    def test_full_flow_and_completed_state_is_unchanged(self):
        state = self.create()
        session_id = state["session_id"]
        for answer in ("30", "mild cough", "two days", "3", "none", "no", "yes"):
            response = self.message(session_id, answer)
            self.assertEqual(response.status_code, 200)
            state = response.json()
        self.assertTrue(state["done"])
        self.assertFalse(state["emergency"])
        self.assertEqual(state["collected"], {
            "age": 30, "symptoms": "mild cough", "duration": "two days",
            "severity": 3, "medications": "none", "allergies": "no",
        })
        self.assertEqual(self.message(session_id, "no").json(), state)

    def test_invalid_answer_reasks_and_no_confirmation_resets(self):
        session_id = self.create()["session_id"]
        response = self.message(session_id, "not a number")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["step"], "age")
        self.assertIsNone(response.json()["collected"]["age"])
        for answer in ("30", "mild cough", "two days", "3", "none", "none", "no"):
            state = self.message(session_id, answer).json()
        self.assertEqual(state["step"], "age")
        self.assertTrue(all(value is None for value in state["collected"].values()))

    def test_red_flag_is_not_collected_and_is_terminal(self):
        session_id = self.create()["session_id"]
        self.message(session_id, "30")
        response = self.message(session_id, "Synthetic CHEST PAIN")
        self.assertEqual(response.status_code, 200)
        state = response.json()
        self.assertTrue(state["done"])
        self.assertTrue(state["emergency"])
        self.assertIsNone(state["collected"]["symptoms"])
        self.assertEqual(state["collected"]["age"], 30)
        self.assertEqual(self.message(session_id, "two days").json(), state)

    def test_unknown_session(self):
        response = self.message("unknown-session", "synthetic")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {
            "error": {"code": "http_404", "message": "Not Found"}
        })
        ErrorResponse.model_validate(response.json())

    def test_invalid_bodies_do_not_echo_input_or_change_state(self):
        session_id = self.create()["session_id"]
        for body in (
            {"message": ""}, {"message": "x" * 2001}, {"message": 30},
            {"message": None}, {}, [],
        ):
            with self.subTest(body_type=type(body).__name__):
                response = self.client.post(
                    f"/v1/chat/sessions/{session_id}/messages", json=body
                )
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(), {
                    "error": {
                        "code": "validation_error", "message": "Request validation failed"
                    }
                })
                self.assertIsNone(self.stored_session(session_id)["age"])
        response = self.message(session_id, " ")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["step"], "age")

    def test_sessions_are_isolated(self):
        first = self.create()["session_id"]
        second = self.create()["session_id"]
        self.message(first, "30")
        self.assertIsNone(self.stored_session(second)["age"])

    def test_demo_is_self_contained_html(self):
        response = self.client.get("/demo")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("نسخهٔ نمایشی", response.text)
        self.assertIn('lang="fa" dir="rtl"', response.text)
        self.assertIn("textContent", response.text)
        self.assertNotIn("innerHTML", response.text)
        self.assertNotIn("<script src=", response.text)


    def test_full_persian_flow(self):
        state = self.create()
        session_id = state["session_id"]
        for answer in ("۳۰", "سرفه خفیف", "دو روز", "۳", "هیچ", "ندارد", "بله"):
            response = self.message(session_id, answer)
            self.assertEqual(response.status_code, 200)
            state = response.json()
        self.assertTrue(state["done"])
        self.assertFalse(state["emergency"])
        self.assertEqual(state["collected"], {
            "age": 30, "symptoms": "سرفه خفیف", "duration": "دو روز",
            "severity": 3, "medications": "هیچ", "allergies": "ندارد",
        })
        self.assertIn("پایان", state["reply"])

    def test_dropdown_answer_values_complete_intake(self):
        session_id = self.create()["session_id"]
        for answer in ("۳۰", "سرفه خفیف", "دو تا سه روز", "۳", "هیچ", "ندارد", "بله"):
            response = self.message(session_id, answer)
            self.assertEqual(response.status_code, 200)
            state = response.json()
        self.assertTrue(state["done"])
        self.assertFalse(state["emergency"])
        self.assertEqual(state["collected"], {
            "age": 30, "symptoms": "سرفه خفیف", "duration": "دو تا سه روز",
            "severity": 3, "medications": "هیچ", "allergies": "ندارد",
        })
