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
from helpers import as_patient, intake_answers, patient_of, register_patient
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
            ("age", "height_cm", "weight_kg", "chief_complaint", "symptoms", "duration", "severity", "medical_history", "medications", "medication_history", "food_allergies", "allergies", "additional_context")
        ))

    def test_full_flow_and_completed_state_is_unchanged(self):
        state = self.create()
        session_id = state["session_id"]
        for answer in intake_answers(symptoms="mild cough", allergies="no"):
            response = self.message(session_id, answer)
            self.assertEqual(response.status_code, 200)
            state = response.json()
        self.assertTrue(state["done"])
        self.assertFalse(state["emergency"])
        self.assertEqual(state["collected"], {
            "age": 30, "symptoms": "mild cough", "duration": "two days",
            "severity": 3, "medications": "none", "allergies": "no",
            "height_cm": 170.5, "weight_kg": 70.2, "chief_complaint": "synthetic complaint",
            "medical_history": "none", "medication_history": "none", "food_allergies": "none",
            "additional_context": "",
        })
        self.assertEqual(self.message(session_id, "no").json(), state)

    def test_invalid_answer_reasks_and_no_confirmation_resets(self):
        session_id = self.create()["session_id"]
        response = self.message(session_id, "not a number")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["step"], "age")
        self.assertIsNone(response.json()["collected"]["age"])
        for answer in intake_answers(symptoms="mild cough", confirm="no"):
            state = self.message(session_id, answer).json()
        self.assertEqual(state["step"], "age")
        self.assertTrue(all(value is None for value in state["collected"].values()))

    def test_red_flag_is_not_collected_and_is_terminal(self):
        session_id = self.create()["session_id"]
        for answer in intake_answers()[:4]:
            self.message(session_id, answer)
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
        for answer in intake_answers("۳۰", "سرفه خفیف", "دو روز", "۳", "هیچ", "ندارد", "بله"):
            response = self.message(session_id, answer)
            self.assertEqual(response.status_code, 200)
            state = response.json()
        self.assertTrue(state["done"])
        self.assertFalse(state["emergency"])
        self.assertEqual(state["collected"], {
            "age": 30, "symptoms": "سرفه خفیف", "duration": "دو روز",
            "severity": 3, "medications": "هیچ", "allergies": "ندارد",
            "height_cm": 170.5, "weight_kg": 70.2, "chief_complaint": "synthetic complaint",
            "medical_history": "none", "medication_history": "none", "food_allergies": "none",
            "additional_context": "",
        })
        self.assertIn("پایان", state["reply"])

    def test_dropdown_answer_values_complete_intake(self):
        session_id = self.create()["session_id"]
        for answer in intake_answers("۳۰", "سرفه خفیف", "دو تا سه روز", "۳", "هیچ", "ندارد", "بله"):
            response = self.message(session_id, answer)
            self.assertEqual(response.status_code, 200)
            state = response.json()
        self.assertTrue(state["done"])
        self.assertFalse(state["emergency"])
        self.assertEqual(state["collected"], {
            "age": 30, "symptoms": "سرفه خفیف", "duration": "دو تا سه روز",
            "severity": 3, "medications": "هیچ", "allergies": "ندارد",
            "height_cm": 170.5, "weight_kg": 70.2, "chief_complaint": "synthetic complaint",
            "medical_history": "none", "medication_history": "none", "food_allergies": "none",
            "additional_context": "",
        })

    def review(self):
        state = self.create()
        for answer in intake_answers(additional_context="doctor-only synthetic note")[:-1]:
            state = self.message(state["session_id"], answer).json()
        self.assertEqual(state["step"], "confirm")
        self.assertFalse(state["done"])
        return state

    def test_edit_each_answer_preserves_others_and_requires_confirmation(self):
        state = self.review()
        changes = {
            "age": ("۳۵", 35), "height_cm": ("۱۸۰٫۵", 180.5), "weight_kg": ("۸۰", 80.0),
            "chief_complaint": ("updated synthetic complaint", "updated synthetic complaint"),
            "symptoms": ("تب", "تب"), "duration": ("three days", "three days"), "severity": ("4", 4),
            "medical_history": ("synthetic history", "synthetic history"), "medications": ("ibuprofen", "ibuprofen"),
            "medication_history": ("past synthetic medicine", "past synthetic medicine"),
            "food_allergies": ("synthetic food", "synthetic food"), "allergies": ("synthetic allergy", "synthetic allergy"),
            "additional_context": ("new note\n<script>inert</script>", "new note\n<script>inert</script>"),
        }
        for name, (message, expected) in changes.items():
            before = dict(state["collected"])
            response = self.client.post(f"/v1/chat/sessions/{state['session_id']}/messages", json={"message": message, "edit_field": name})
            self.assertEqual(response.status_code, 200, name)
            state = response.json()
            self.assertEqual(state["collected"], {**before, name: expected})
            self.assertEqual(state["step"], "confirm")
            self.assertFalse(state["done"])
        self.assertEqual([entry["code"] for entry in state["matched"]["symptoms"]], ["fever"])
        self.assertEqual([entry["code"] for entry in state["matched"]["medicines"]], ["ibuprofen"])
        self.assertEqual(self.client.get("/v1/me/history").json()[0]["collected"], state["collected"])
        state = self.message(state["session_id"], "بله").json()
        self.assertTrue(state["done"])
        before = dict(self.stored_session(state["session_id"]))
        response = self.client.post(f"/v1/chat/sessions/{state['session_id']}/messages", json={"message": "40", "edit_field": "age"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(dict(self.stored_session(state["session_id"])), before)
        self.assertEqual(self.message(state["session_id"], "ignored").json(), state)

    def test_invalid_review_edits_are_private_atomic_and_owned(self):
        state = self.create()
        path = f"/v1/chat/sessions/{state['session_id']}/messages"
        self.assertEqual(self.client.post(path, json={"message": "35", "edit_field": "age"}).status_code, 409)
        state = self.review()
        path = f"/v1/chat/sessions/{state['session_id']}/messages"
        before = self.client.get("/v1/me/history").json()
        for name, message in (("age", "private-invalid-answer"), ("weight_kg", "-1"), ("symptoms", " "),
                              ("confirm", "yes"), ("profile", "yes"), ("unknown", "value"), ("additional_context", "x" * 2001)):
            response = self.client.post(path, json={"message": message, "edit_field": name})
            self.assertEqual(response.status_code, 422)
            self.assertNotIn("private-invalid-answer", response.text)
        self.assertEqual(self.client.get("/v1/me/history").json(), before)
        register_patient(self.client)
        self.assertEqual(self.client.post(path, json={"message": "35", "edit_field": "age"}).status_code, 404)

    def test_review_red_flags_still_redact_the_answer(self):
        for name in ("chief_complaint", "symptoms"):
            state = self.review()
            marker = "private_edit_marker CHEST PAIN"
            response = self.client.post(f"/v1/chat/sessions/{state['session_id']}/messages", json={"message": marker, "edit_field": name})
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertTrue(result["done"])
            self.assertTrue(result["emergency"])
            self.assertEqual(result["collected"], state["collected"])
            self.assertNotIn(marker, self.client.get("/v1/me/history").text)
