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
from helpers import admin_account, as_patient, intake_answers, patient_of, register_doctor, register_patient
from app.agent import sessions, triage
from app.core import db, llm
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

    def test_demo_uses_shared_local_assets(self):
        response = self.client.get("/demo")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("نسخهٔ نمایشی", response.text)
        self.assertIn('lang="fa" dir="rtl"', response.text)
        self.assertIn("textContent", response.text)
        self.assertNotIn("innerHTML", response.text)
        self.assertIn('<script src="/assets/shell.js">', response.text)
        self.assertIn('href="/assets/shell.css"', response.text)

    def test_shell_assets_allowlist_cache_markup_and_safe_rendering(self):
        for name, mime in (("shell.css", "text/css"), ("shell.js", "text/javascript")):
            response = self.client.get("/assets/" + name)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.headers["content-type"].startswith(mime))
            self.assertEqual(response.headers["cache-control"], "no-cache")
        for path in ("/assets/unknown.js", "/assets/index.html", "/assets/%2e%2e%2findex.html", "/assets/..%5cindex.html", "/assets/data/doctors.json"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, path)
            ErrorResponse.model_validate(response.json())
        for path in ("/demo", "/doctor", "/admin"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.headers["content-type"].startswith("text/html"))
            for marker in ('href="/assets/shell.css"', '<script src="/assets/shell.js">', 'id="menu-toggle"', 'aria-expanded="false"', 'aria-controls="shell-sidebar"', '<nav id="shell-nav" aria-label='):
                self.assertIn(marker, response.text)
        static = Path(__file__).parents[1] / "src/app/static"
        for path in [*static.glob("*.html"), *static.glob("*.js")]:
            for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
                self.assertNotIn(forbidden, path.read_text(encoding="utf-8"), str(path))
        self.assertNotIn("/v1/me/history", (static / "index.html").read_text(encoding="utf-8"))

    def test_conversation_list_states_order_summaries_and_read_only(self):
        expected = {}
        for index, status in enumerate(("intake", "triage", "pending", "expired", "accepted", "ended", "cancelled", "expired", "emergency")):
            state = self.create()
            session_id = state["session_id"]
            expected[session_id] = status
            with closing(connect()) as connection, connection:
                connection.execute("UPDATE sessions SET created_at=?,done=?,emergency=?,chief_complaint=?,symptoms=? WHERE id=?", (
                    f"2040-01-{index+1:02}T00:00:00+00:00", status != "intake", status == "emergency",
                    "x" * 90 if index == 0 else None, "synthetic symptoms" if index else None, session_id))
                if index == 1:
                    connection.execute("""INSERT INTO triage_results(session_id,specialty_code,urgency,source,doctor_summary_fa,considerations_fa,created_at)
                        VALUES (?,'general_practice','unknown','fallback','','[]','2040-01-01')""", (session_id,))
                if index >= 2:
                    stored_status = "pending" if index == 3 else "accepted" if status == "ended" else "cancelled" if status == "emergency" else status
                    connection.execute("""INSERT INTO visit_requests(id,patient_id,session_id,specialty_code,status,created_at,updated_at,ended_at,doctor_id)
                        VALUES (?,?,?,'general_practice',?,?,?,?,?)""", (f"request-{index}", self.user["patient_id"], session_id, stored_status,
                        "2000-01-01" if index == 3 else "2040-01-01", "2040-01-01", "2040-01-02" if status == "ended" else None,
                        "demo_doctor_1" if stored_status == "accepted" else None))
        with closing(connect()) as connection:
            before = list(connection.iterdump())
        response = self.client.get("/v1/chat/sessions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        items = response.json()
        self.assertEqual([item["session_id"] for item in items], list(reversed(expected)))
        self.assertEqual({item["session_id"]: item["status"] for item in items}, expected)
        self.assertEqual(items[-1]["summary"], "x" * 80)
        self.assertEqual(items[0]["summary"], "synthetic symptoms")
        self.assertEqual(items[0]["request_id"], "request-8")
        self.assertEqual(items[0]["specialty"]["code"], "general_practice")
        self.assertIsNone(items[-1]["specialty"])
        for item in items:
            self.assertEqual(set(item), {"session_id", "created_at", "summary", "step", "done", "emergency", "status", "specialty", "request_id"})
        with closing(connect()) as connection:
            self.assertEqual(list(connection.iterdump()), before)
            self.assertEqual(connection.execute("SELECT status FROM visit_requests WHERE id='request-3'").fetchone()[0], "pending")
        self.assertEqual(len(self.client.get("/v1/chat/sessions?limit=2").json()), 2)
        for limit in (0, 51, "invalid"):
            invalid = self.client.get(f"/v1/chat/sessions?limit={limit}")
            self.assertEqual(invalid.status_code, 422)
            ErrorResponse.model_validate(invalid.json())

    def test_conversation_list_is_one_query_and_uses_stored_specialty_first(self):
        state = self.create()
        self.assertIsNone(self.client.get("/v1/chat/sessions").json()[0]["summary"])
        with closing(connect()) as connection, connection:
            connection.execute("INSERT INTO triage_results(session_id,specialty_code,urgency,source,doctor_summary_fa,considerations_fa,created_at) VALUES (?,'general_practice','unknown','fallback','','[]','2040-01-01')", (state["session_id"],))
            connection.execute("INSERT INTO visit_requests(id,patient_id,session_id,specialty_code,status,created_at,updated_at) VALUES ('old',?,?,'dermatology','cancelled','2040-01-01','2040-01-01')", (self.user["patient_id"], state["session_id"]))
            connection.execute("INSERT INTO visit_requests(id,patient_id,session_id,specialty_code,status,created_at,updated_at) VALUES ('new',?,?,'dermatology','expired','2040-01-01','2040-01-01')", (self.user["patient_id"], state["session_id"]))
        statements = []
        original = db.connect
        def traced():
            connection = original()
            connection.set_trace_callback(statements.append)
            return connection
        with patch.object(db, "connect", side_effect=traced):
            items = sessions.list_sessions(self.user["patient_id"])
        self.assertEqual(len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]), 1)
        self.assertEqual(items[0]["specialty"]["code"], "general_practice")
        self.assertEqual(items[0]["request_id"], "new")
        self.assertEqual(items[0]["status"], "expired")

    def test_conversation_reads_are_owned_and_patient_only(self):
        state = self.create()
        detail_path = "/v1/chat/sessions/" + state["session_id"]
        other = register_patient(self.client)
        self.assertNotEqual(other["patient_id"], self.user["patient_id"])
        self.assertEqual(self.client.get("/v1/chat/sessions").json(), [])
        for path in (detail_path, "/v1/chat/sessions/unknown"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)
            ErrorResponse.model_validate(response.json())
        doctor = self.enterContext(TestClient(app))
        register_doctor(doctor)
        admin = self.enterContext(TestClient(app))
        with admin_account(admin):
            for client in (doctor, admin):
                for path in ("/v1/chat/sessions", detail_path):
                    self.assertEqual(client.get(path).status_code, 403)

    def test_conversation_detail_state_stored_triage_latest_request_and_privacy(self):
        state = self.create()
        path = "/v1/chat/sessions/" + state["session_id"]
        detail = self.client.get(path).json()
        self.assertEqual(detail["session"], state)
        self.assertIsNone(detail["triage"])
        self.assertIsNone(detail["request"])
        self.assertEqual(detail["transcript"][0]["content"], state["reply"])
        for answer in intake_answers():
            state = self.message(state["session_id"], answer).json()
        for source in ("llm", "fallback"):
            with closing(connect()) as connection, connection:
                connection.execute("DELETE FROM triage_results")
                connection.execute("INSERT INTO triage_results(session_id,specialty_code,urgency,source,doctor_summary_fa,considerations_fa,created_at) VALUES (?,'general_practice','routine',?,'private doctor summary','[\"private consideration\"]','2040-01-01')", (state["session_id"], source))
            with patch.dict(os.environ, {"APP_LLM_BASE_URL": "http://provider.invalid/v1", "APP_LLM_MODEL": "synthetic-model"}), \
                    patch.object(triage, "run_triage", side_effect=AssertionError("must only read stored triage")) as run, \
                    patch.object(llm, "chat_completion", side_effect=AssertionError("must not call provider")) as provider:
                response = self.client.get(path)
            run.assert_not_called()
            provider.assert_not_called()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.json()["session"], state)
            self.assertEqual(response.json()["triage"]["source"], source)
            for marker in ("doctor_summary", "considerations", "private doctor", "private consideration", "patient_id", "username"):
                self.assertNotIn(marker, response.text)
        with closing(connect()) as connection, connection:
            for index, status in enumerate(("cancelled", "expired")):
                connection.execute("INSERT INTO visit_requests(id,patient_id,session_id,specialty_code,status,created_at,updated_at) VALUES (?,?,?,'general_practice',?,'2040-01-01','2040-01-01')", (str(index), self.user["patient_id"], state["session_id"], status))
            before = list(connection.iterdump())
        detail = self.client.get(path).json()
        self.assertEqual(detail["request"]["id"], "1")
        self.assertEqual(detail["request"]["session_id"], state["session_id"])
        self.assertIsNone(detail["request"]["accepted_at"])
        self.assertIsNone(detail["request"]["ended_at"])
        with closing(connect()) as connection:
            self.assertEqual(list(connection.iterdump()), before)
            expected = [dict(row) for row in connection.execute("SELECT role,content,created_at FROM messages WHERE session_id=? ORDER BY id", (state["session_id"],))]
        self.assertEqual(detail["transcript"], expected)

    def test_conversation_transcript_cap_order_and_emergency_redaction(self):
        state = self.create()
        path = "/v1/chat/sessions/" + state["session_id"]
        marker = "private original chest pain"
        self.message(state["session_id"], "30")
        self.message(state["session_id"], "170")
        self.message(state["session_id"], "70")
        self.message(state["session_id"], marker)
        response = self.client.get(path)
        self.assertNotIn(marker, response.text)
        self.assertTrue(response.json()["session"]["emergency"])
        self.assertIn(sessions.REDACTED_MESSAGE, [item["content"] for item in response.json()["transcript"]])
        with closing(connect()) as connection, connection:
            for index in range(205):
                db.add_message(connection, state["session_id"], "user", f"synthetic-{index}", "2040-01-01")
            expected = [dict(row) for row in connection.execute("SELECT role,content,created_at FROM messages WHERE session_id=? ORDER BY id LIMIT 200", (state["session_id"],))]
        detail = self.client.get(path).json()
        self.assertEqual(len(detail["transcript"]), 200)
        self.assertEqual(detail["transcript"], expected)


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
