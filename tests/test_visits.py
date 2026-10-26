import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core import db, llm
from app.main import app
from app.services import doctors, visits
from helpers import intake_answers, register_doctor, register_patient

BASE = "2030-01-01T00:00:00.000000+00:00"


class VisitTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {
            "APP_DB_PATH": str(Path(directory) / "visits.db"), "APP_DOCTOR_AUTO_VERIFY": "true",
            "APP_DEMO_DOCTOR_PASSWORD": "", "APP_COOKIE_SECURE": "false",
            "APP_SESSION_TTL_HOURS": "12", "APP_REQUEST_TTL_MINUTES": "30",
            "APP_LLM_BASE_URL": "", "APP_LLM_MODEL": "",
        }))
        self.clock = self.enterContext(patch.object(db, "utc_now", return_value=BASE))
        self.patient = self.enterContext(TestClient(app))
        self.user = register_patient(self.patient)
        self.doctor_clients = [TestClient(app), TestClient(app)]
        for client in self.doctor_clients:
            self.addCleanup(client.close)
        self.doctor_rows = [register_doctor(client) for client in self.doctor_clients]
        for client in self.doctor_clients:
            self.assertEqual(client.get("/v1/doctor/requests").status_code, 200)

    def complete(self, triage=True, additional_context="رد کردن"):
        response = self.patient.post("/v1/chat/sessions")
        self.assertEqual(response.status_code, 201)
        state = response.json()
        path = f"/v1/chat/sessions/{state['session_id']}/messages"
        if state["step"] == "profile":
            self.assertEqual(self.patient.post(path, json={"message": "no"}).status_code, 200)
        for answer in intake_answers(medications="ibuprofen", additional_context=additional_context):
            response = self.patient.post(path, json={"message": answer})
            self.assertEqual(response.status_code, 200)
        state = response.json()
        self.assertTrue(state["done"])
        if triage:
            self.assertEqual(self.patient.post(f"/v1/chat/sessions/{state['session_id']}/triage").status_code, 200)
        return state

    def create_request(self, state):
        response = self.patient.post("/v1/visit-requests", json={"session_id": state["session_id"]})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def assert_conflict(self, response, code):
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], code)
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_broadcast_preview_atomic_accept_and_private_full_details(self):
        self.complete(additional_context="previous_doctor_note_marker")
        state = self.complete(additional_context="current_doctor_note_marker")
        request = self.create_request(state)
        queues = [client.get("/v1/doctor/requests", params={"status": "pending"}).json() for client in self.doctor_clients]
        for queue in queues:
            self.assertEqual(len(queue), 1)
            item = queue[0]
            self.assertEqual(item["id"], request["id"])
            self.assertIsNone(item["patient"])
            self.assertIsNone(item["previous_visits"])
            self.assertIsNone(item["ai"])
            self.assertEqual(item["preview"], {"age": 30, "symptoms": "cough", "duration": "two days", "severity": 3})
            self.assertEqual(set(item), {"id","status","created_at","specialty","urgency","preview","patient","previous_visits","ai","ended"})
            self.assertNotIn("doctor_note_marker", json.dumps(item))
        barrier = Barrier(2)
        def accept(index):
            barrier.wait(timeout=10)
            return index, self.doctor_clients[index].post(f"/v1/doctor/requests/{request['id']}/accept")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(accept, range(2)))
        self.assertEqual(sorted(response.status_code for _, response in results), [200, 409])
        winner = next(index for index, response in results if response.status_code == 200)
        loser = 1 - winner
        accepted = next(response.json() for _, response in results if response.status_code == 200)
        self.assertEqual(accepted["patient"]["medications"], "ibuprofen")
        self.assertEqual(accepted["patient"]["additional_context"], "current_doctor_note_marker")
        self.assertEqual(accepted["previous_visits"][0]["additional_context"], "previous_doctor_note_marker")
        for name, value in {"height_cm": 170.5, "weight_kg": 70.2, "chief_complaint": "synthetic complaint",
                            "medical_history": "none", "medication_history": "none", "food_allergies": "none"}.items():
            self.assertEqual(accepted["patient"][name], value)
            self.assertEqual(accepted["previous_visits"][0][name], value)
        self.assertEqual(len(accepted["previous_visits"]), 1)
        self.assertEqual(accepted["ai"]["source"], "fallback")
        self.assertEqual(accepted["ai"]["notice"], visits.AI_NOTICE)
        self.assertEqual(self.doctor_clients[loser].get("/v1/doctor/requests").json(), [])
        winner_items = self.doctor_clients[winner].get("/v1/doctor/requests", params={"status": "accepted"}).json()
        self.assertEqual(winner_items, [accepted])
        patient_items = self.patient.get("/v1/visit-requests").json()
        self.assertEqual(patient_items[0]["status"], "accepted")
        self.assertEqual(patient_items[0]["doctor"]["id"], self.doctor_rows[winner]["id"])
        for response in [*queues, accepted, winner_items]:
            serialized = json.dumps(response)
            for forbidden in (self.user["patient_id"], self.user["id"], self.user["username"], state["session_id"], "patient_id", "username"):
                self.assertNotIn(forbidden, serialized)
        with closing(db.connect()) as connection:
            rows = connection.execute("SELECT * FROM visit_requests").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doctor_id"], self.doctor_rows[winner]["id"])
        self.assertIsNotNone(rows[0]["accepted_at"])

    def test_every_visit_creation_guard_and_partial_unique_index(self):
        response = self.patient.post("/v1/visit-requests", json={"session_id": "unknown"})
        self.assertEqual(response.status_code, 404)
        incomplete = self.patient.post("/v1/chat/sessions").json()
        self.assert_conflict(self.patient.post("/v1/visit-requests", json={"session_id": incomplete["session_id"]}), "intake_not_ready")
        path = f"/v1/chat/sessions/{incomplete['session_id']}/messages"
        self.patient.post(path, json={"message": "30"})
        self.patient.post(path, json={"message": "chest pain"})
        self.assert_conflict(self.patient.post("/v1/visit-requests", json={"session_id": incomplete["session_id"]}), "intake_not_ready")
        missing = self.complete(triage=False)
        self.assert_conflict(self.patient.post("/v1/visit-requests", json={"session_id": missing["session_id"]}), "triage_required")
        with closing(db.connect()) as connection, connection:
            connection.execute(
                """INSERT INTO triage_results(session_id,specialty_code,urgency,source,doctor_summary_fa,considerations_fa,created_at)
                   VALUES (?,'general_practice','emergency','llm','','[]',?)""", (missing["session_id"], BASE),
            )
        self.assert_conflict(self.patient.post("/v1/visit-requests", json={"session_id": missing["session_id"]}), "emergency_triage")
        state = self.complete()
        request = self.create_request(state)
        self.assert_conflict(self.patient.post("/v1/visit-requests", json={"session_id": state["session_id"]}), "active_request_exists")
        self.assertEqual(self.doctor_clients[0].post(f"/v1/doctor/requests/{request['id']}/accept").status_code, 200)
        self.assert_conflict(self.patient.post("/v1/visit-requests", json={"session_id": state["session_id"]}), "active_request_exists")

    def test_no_online_doctor_and_presence_boundaries(self):
        state = self.complete()
        self.clock.return_value = "2030-01-01T00:00:45.000000+00:00"
        online = doctors.for_specialty("general_practice")
        self.assertEqual(sum(item["online"] for item in online), 2)
        self.clock.return_value = "2030-01-01T00:00:45.000001+00:00"
        self.assertFalse(any(item["online"] for item in doctors.for_specialty("general_practice")))
        self.assert_conflict(self.patient.post("/v1/visit-requests", json={"session_id": state["session_id"]}), "no_online_doctor")
        self.assertEqual(self.doctor_clients[0].get("/v1/doctor/requests").status_code, 200)
        self.assertEqual(sum(item["online"] for item in doctors.for_specialty("general_practice")), 1)
        self.create_request(state)

    def test_unavailable_doctor_queue_hidden_and_accept_blocked(self):
        state = self.complete()
        request = self.create_request(state)
        response = self.doctor_clients[0].put("/v1/doctor/availability", json={"available": False})
        self.assertEqual(response.json(), {"available": False})
        self.assertEqual(self.doctor_clients[0].get("/v1/doctor/requests").json(), [])
        self.assert_conflict(self.doctor_clients[0].post(f"/v1/doctor/requests/{request['id']}/accept"), "doctor_unavailable")
        self.assertFalse(next(item["online"] for item in doctors.for_specialty("general_practice") if item["id"] == self.doctor_rows[0]["id"]))
        self.assertEqual(len(self.doctor_clients[1].get("/v1/doctor/requests").json()), 1)
        self.assertEqual(self.doctor_clients[0].put("/v1/doctor/availability", json={"available": True}).status_code, 200)
        self.assertEqual(len(self.doctor_clients[0].get("/v1/doctor/requests").json()), 1)

    def test_unverified_doctor_absent_from_lists_and_never_counts_online(self):
        client = TestClient(app)
        self.addCleanup(client.close)
        with patch.dict(os.environ, {"APP_DOCTOR_AUTO_VERIFY": "false"}):
            unverified = register_doctor(client)
        self.assertEqual(client.get("/v1/doctor/requests").status_code, 403)
        with closing(db.connect()) as connection, connection:
            connection.execute("UPDATE doctors SET last_seen_at=? WHERE id=?", (BASE, unverified["id"]))
        state = self.complete()
        triage = self.patient.post(f"/v1/chat/sessions/{state['session_id']}/triage").json()
        self.assertNotIn(unverified["id"], [doctor["id"] for doctor in triage["doctors"]])
        for doctor in self.doctor_clients:
            doctor.put("/v1/doctor/availability", json={"available": False})
        self.assert_conflict(self.patient.post("/v1/visit-requests", json={"session_id": state["session_id"]}), "no_online_doctor")

    def test_other_specialty_never_sees_or_accepts_request(self):
        other = TestClient(app)
        self.addCleanup(other.close)
        register_doctor(other, specialty="ent")
        state = self.complete()
        request = self.create_request(state)
        self.assertEqual(other.get("/v1/doctor/requests").json(), [])
        self.assertEqual(other.post(f"/v1/doctor/requests/{request['id']}/accept").status_code, 404)
        self.assertEqual(other.post("/v1/doctor/requests/unknown/accept").status_code, 404)

    def test_ownership_hides_sessions_messages_triage_and_requests(self):
        state = self.complete()
        request = self.create_request(state)
        other = TestClient(app)
        self.addCleanup(other.close)
        register_patient(other)
        for path, body in (
            (f"/v1/chat/sessions/{state['session_id']}/messages", {"message": "99"}),
            (f"/v1/chat/sessions/{state['session_id']}/triage", None),
            ("/v1/visit-requests", {"session_id": state["session_id"]}),
            (f"/v1/visit-requests/{request['id']}/cancel", None),
        ):
            response = other.post(path, **({"json": body} if body is not None else {}))
            self.assertEqual(response.status_code, 404)
        self.assertEqual(other.get("/v1/visit-requests").json(), [])
        self.assertEqual(other.get("/v1/me/history").json(), [])
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT age FROM sessions WHERE id=?", (state["session_id"],)).fetchone()[0], 30)

    def test_cancel_re_request_and_non_pending_cancel_guards(self):
        state = self.complete()
        request = self.create_request(state)
        path = f"/v1/visit-requests/{request['id']}/cancel"
        self.assertEqual(self.patient.post(path).json()["status"], "cancelled")
        self.assert_conflict(self.patient.post(path), "request_not_pending")
        replacement = self.create_request(state)
        self.doctor_clients[0].post(f"/v1/doctor/requests/{replacement['id']}/accept")
        self.assert_conflict(self.patient.post(f"/v1/visit-requests/{replacement['id']}/cancel"), "request_not_pending")
        self.assertEqual(self.patient.post("/v1/visit-requests/unknown/cancel").status_code, 404)
        rows = self.patient.get("/v1/visit-requests").json()
        self.assertEqual([item["id"] for item in rows], [replacement["id"], request["id"]])

    def test_expiry_sweep_persists_even_when_accept_or_cancel_conflicts(self):
        state = self.complete()
        request = self.create_request(state)
        self.clock.return_value = "2030-01-01T00:30:00.000001+00:00"
        self.assert_conflict(self.doctor_clients[0].post(f"/v1/doctor/requests/{request['id']}/accept"), "request_not_pending")
        self.assert_conflict(self.patient.post(f"/v1/visit-requests/{request['id']}/cancel"), "request_not_pending")
        self.assertEqual(self.patient.get("/v1/visit-requests").json()[0]["status"], "expired")
        self.doctor_clients[0].get("/v1/doctor/requests")
        replacement = self.create_request(state)
        self.assertNotEqual(replacement["id"], request["id"])

    def test_request_ttl_configuration_and_list_sweeps(self):
        with patch.dict(os.environ, {"APP_REQUEST_TTL_MINUTES": "1"}):
            request = self.create_request(self.complete())
            self.clock.return_value = "2030-01-01T00:01:00.000001+00:00"
            self.assertEqual(self.doctor_clients[1].get("/v1/doctor/requests").json(), [])
            self.assertEqual(self.patient.get("/v1/visit-requests").json()[0]["status"], "expired")
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT status FROM visit_requests WHERE id=?", (request["id"],)).fetchone()[0], "expired")

    def test_doctor_list_online_score_null_order_and_nullable_response(self):
        with closing(db.connect()) as connection, connection:
            connection.execute("UPDATE doctors SET score=4.0 WHERE id=?", (self.doctor_rows[0]["id"],))
        result = doctors.for_specialty("general_practice")
        self.assertEqual([doctor["id"] for doctor in result[:2]], [self.doctor_rows[0]["id"], self.doctor_rows[1]["id"]])
        self.assertTrue(all(doctor["online"] for doctor in result[:2]))
        self.assertIsNone(result[1]["score"])
        self.assertEqual([doctor["score"] for doctor in result[2:]], [4.9, 4.2])
        state = self.complete()
        response = self.patient.post(f"/v1/chat/sessions/{state['session_id']}/triage")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["doctors"], result)

    def test_delete_patient_cascades_account_tokens_intakes_triage_and_requests(self):
        state = self.complete()
        request = self.create_request(state)
        self.doctor_clients[0].post(f"/v1/doctor/requests/{request['id']}/accept")
        response = self.patient.delete("/v1/me")
        self.assertEqual(response.status_code, 204)
        self.assertIn("Max-Age=0", response.headers["set-cookie"])
        self.assertEqual(self.patient.get("/v1/auth/me").status_code, 401)
        with closing(db.connect()) as connection:
            for table in ("patients", "users"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE id=?", (self.user["patient_id"] if table == "patients" else self.user["id"],)).fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM auth_sessions WHERE user_id=?", (self.user["id"],)).fetchone()[0], 0)
            for table in ("sessions", "messages", "triage_results", "visit_requests"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM doctors").fetchone()[0], 14)

    def test_validation_and_role_errors_use_no_store(self):
        for body in ({"session_id": ""}, {"session_id": 12}, {"session_id": "id", "doctor_id": "forged"}, {}):
            response = self.patient.post("/v1/visit-requests", json=body)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.headers["cache-control"], "no-store")
        for available in ("true", 1, None):
            self.assertEqual(self.doctor_clients[0].put("/v1/doctor/availability", json={"available": available}).status_code, 422)
        self.assertEqual(self.doctor_clients[0].get("/v1/doctor/requests?status=expired").status_code, 422)
        self.assertEqual(self.doctor_clients[0].get("/v1/me/history").status_code, 403)
        self.assertEqual(self.patient.put("/v1/doctor/availability", json={"available": True}).status_code, 403)
