import copy
import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier, Event
from unittest.mock import patch

import httpx

from fastapi.testclient import TestClient

from app.agent import doctors, triage
from app.services import doctors as stored_doctors
from app.agent.context import build_context
from app.agent.intake import EMERGENCY_REPLY
from app.core import db, llm
from app.main import app
from helpers import as_patient, intake_answers, patient_of, register_patient

VALID = {
    "specialty_code": "internal_medicine", "urgency": "soon",
    "reason_fa": "پیشنهاد تخصص برای مرور اطلاعات ثبت‌شده.",
    "doctor_summary_fa": "خلاصهٔ آزمایشی فقط برای پزشک",
    "considerations_fa": ["ملاحظهٔ تأییدنشدهٔ آزمایشی"],
}


class DoctorTests(unittest.TestCase):
    def test_file_contains_synthetic_doctors_and_expected_specialties(self):
        document = doctors.load_file(doctors.DATA_FILE)
        self.assertEqual(len(document["specialties"]), 9)
        self.assertEqual(len(document["doctors"]), 12)
        for code in ("general_practice", "internal_medicine"):
            self.assertGreaterEqual(sum(item["specialty_code"] == code for item in document["doctors"]), 2)
        for doctor in document["doctors"]:
            self.assertTrue(doctor["name_fa"].startswith("پزشک فرضی "))
            self.assertTrue(3.8 <= doctor["score"] <= 4.9)
            self.assertEqual(doctor["score"], round(doctor["score"], 1))

    def test_validation_failures_are_sanitized(self):
        original = doctors.load_doctors()
        invalid = [[], {}, {**original, "status": "private-document"}]
        for field, value in (
            ("id", "Invalid-ID"), ("id", None), ("name_fa", ""),
            ("specialty_code", "unknown"), ("specialty_code", []),
            ("score", -1), ("score", 6), ("score", True), ("score", "4"),
            ("score", float("nan")), ("score", float("inf")),
            ("expertise", []), ("expertise", ["", "private-document"]),
            ("expertise", "private-document"), ("expertise", [None, "value"]),
        ):
            document = copy.deepcopy(original)
            document["doctors"][0][field] = value
            invalid.append(document)
        for field, value in (("code", "Invalid-Code"), ("code", []), ("name_fa", ""), ("name_en", None)):
            document = copy.deepcopy(original)
            document["specialties"][0][field] = value
            invalid.append(document)
        for key in ("specialties", "doctors"):
            document = copy.deepcopy(original)
            document[key].append(copy.deepcopy(document[key][0]))
            invalid.append(document)
            document = copy.deepcopy(original)
            document[key][0] = "private-document"
            invalid.append(document)
        document = copy.deepcopy(original)
        document["doctors"] = [item for item in document["doctors"] if item["specialty_code"] != "general_practice"]
        invalid.append(document)
        document = copy.deepcopy(original)
        document["specialties"] = document["specialties"][1:]
        invalid.append(document)
        for index, document in enumerate(invalid):
            with self.subTest(index=index), patch.object(Path, "read_text", return_value=json.dumps(document)):
                with self.assertRaisesRegex(ValueError, "^doctors.json: id ") as error:
                    doctors.load_file(Path("doctors.json"))
                self.assertNotIn("private-document", str(error.exception))
        for error in (OSError("private-document"), UnicodeError("private-document")):
            with patch.object(Path, "read_text", side_effect=error):
                with self.assertRaisesRegex(ValueError, "^doctors.json: id '<unknown>'$"):
                    doctors.load_file(Path("doctors.json"))
        with patch.object(Path, "read_text", return_value="private-document{"):
            with self.assertRaisesRegex(ValueError, "^doctors.json: id '<unknown>'$"):
                doctors.load_file(Path("doctors.json"))

    def test_filter_online_score_sort_and_ten_limit(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"APP_DB_PATH": str(Path(directory) / "doctors.db")}):
            entries = [
                {"id": f"synthetic_{index}", "name_fa": "synthetic", "expertise": ["one", "two"],
                 "online": index % 2 == 0, "score": 3.8 + index / 100}
                for index in range(12)
            ]
            with closing(db.connect()) as connection, connection:
                for doctor in entries:
                    connection.execute(
                        """INSERT INTO doctors(id,name_fa,specialty_code,expertise,score,verified,last_seen_at,created_at)
                           VALUES (?,?,'general_practice',?,?,1,?,?)""",
                        (doctor["id"], doctor["name_fa"], json.dumps(doctor["expertise"]), doctor["score"],
                         db.utc_now() if doctor["online"] else None, db.utc_now()),
                    )
            result = stored_doctors.for_specialty("general_practice")
        self.assertEqual(len(result), 10)
        self.assertEqual(result, sorted(entries, key=lambda item: (not item["online"], -item["score"]))[:10])

    def test_invalid_doctor_file_stops_startup(self):
        doctors.load_doctors.cache_clear()
        self.addCleanup(doctors.load_doctors.cache_clear)
        with patch.object(doctors, "load_file", side_effect=ValueError("doctors.json: id 'invalid'")):
            with self.assertRaisesRegex(ValueError, "doctors.json"):
                with TestClient(app):
                    self.fail("Started with invalid doctor data")


class TriageTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.db_path = Path(directory) / "test.db"
        self.enterContext(patch.dict(os.environ, {
            "APP_DB_PATH": str(self.db_path), "APP_LLM_BASE_URL": "",
            "APP_LLM_MODEL": "", "APP_LLM_API_KEY": "", "APP_LLM_TIMEOUT_SECONDS": "30",
        }))
        self.client = self.enterContext(TestClient(app))
        self.user = register_patient(self.client)

    def create(self, patient_id=None):
        if patient_id is None:
            self.user = register_patient(self.client)
        else:
            as_patient(self.client, patient_id)
            self.user["patient_id"] = patient_id
        return self.client.post("/v1/chat/sessions").json()

    def complete(self, patient_id=None, additional_context="رد کردن"):
        state = self.create(patient_id)
        path = f"/v1/chat/sessions/{state['session_id']}/messages"
        if state["step"] == "profile":
            self.client.post(path, json={"message": "no"})
        for message in intake_answers(medications="ibuprofen", additional_context=additional_context):
            response = self.client.post(path, json={"message": message})
            self.assertEqual(response.status_code, 200)
        return response.json()

    def endpoint(self, state):
        return f"/v1/chat/sessions/{state['session_id']}/triage"

    def configured(self):
        return patch.dict(os.environ, {"APP_LLM_BASE_URL": "https://provider.test/v1", "APP_LLM_MODEL": "synthetic-model"})

    def assert_fallback(self, response):
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "fallback")
        self.assertEqual(body["specialty"]["code"], "general_practice")
        self.assertEqual(body["urgency"], "unknown")
        self.assertIsNone(body["reason"])
        self.assertFalse(body["emergency"])
        self.assertTrue(body["doctors"])
        with closing(db.connect()) as connection:
            row = connection.execute("SELECT * FROM triage_results WHERE session_id=?", (body["session_id"],)).fetchone()
            self.assertEqual(row["doctor_summary_fa"], "")
            self.assertEqual(json.loads(row["considerations_fa"]), [])

    def test_unconfigured_fallback_is_stored_without_network(self):
        state = self.complete()
        with patch.object(llm, "chat_completion") as call:
            response = self.client.post(self.endpoint(state))
        call.assert_not_called()
        self.assert_fallback(response)

    def test_patient_notes_never_enter_provider_context_current_or_previous(self):
        previous = self.complete(additional_context="previous_doctor_note_marker")
        state = self.complete(patient_of(previous), additional_context="current_doctor_note_marker")
        with self.configured(), patch.object(llm, "chat_completion", return_value=VALID) as call:
            self.assertEqual(self.client.post(self.endpoint(state)).status_code, 200)
        payload = json.dumps(call.call_args.args[1])
        for forbidden in ("previous_doctor_note_marker", "current_doctor_note_marker", "additional_context"):
            self.assertNotIn(forbidden, payload)
        with closing(db.connect()) as connection:
            context = build_context(connection, state["session_id"], for_doctor=True)
        self.assertEqual(context["current"]["additional_context"], "current_doctor_note_marker")
        self.assertEqual(context["previous_visits"][0]["additional_context"], "previous_doctor_note_marker")

    def test_valid_result_stores_private_fields_but_returns_only_public_contract(self):
        state = self.complete()
        with self.configured(), patch.object(llm, "chat_completion", return_value={**VALID, "ignored": "extra"}) as call:
            response = self.client.post(self.endpoint(state))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "llm")
        self.assertEqual(body["specialty"]["code"], VALID["specialty_code"])
        self.assertEqual(body["reason"], VALID["reason_fa"])
        self.assertEqual(body["notice"], triage.NOTICE)
        self.assertEqual(set(body), {"session_id", "source", "specialty", "urgency", "emergency", "reason", "notice", "doctors"})
        expected = stored_doctors.for_specialty("internal_medicine")
        self.assertEqual([item["id"] for item in body["doctors"]], [item["id"] for item in expected])
        self.assertNotIn("doctor_summary_fa", response.text)
        self.assertNotIn("considerations_fa", response.text)
        self.assertNotIn(VALID["doctor_summary_fa"], response.text)
        with closing(db.connect()) as connection:
            row = connection.execute("SELECT * FROM triage_results").fetchone()
            self.assertEqual(row["doctor_summary_fa"], VALID["doctor_summary_fa"])
            self.assertEqual(json.loads(row["considerations_fa"]), VALID["considerations_fa"])
            self.assertEqual(row["model"], "synthetic-model")
        messages = call.call_args.args[1]
        self.assertEqual(messages[0], {"role": "system", "content": triage.SYSTEM_PROMPT})
        context = json.loads(messages[1]["content"])
        self.assertEqual(context["current"]["symptoms"], "cough")
        for identifier in (state["session_id"], patient_of(state)):
            self.assertNotIn(identifier, json.dumps(context))

    def test_invalid_provider_fields_all_fall_back(self):
        variants = [
            {**VALID, "specialty_code": "invented"}, {**VALID, "urgency": "unknown"},
            {**VALID, "reason_fa": "x" * 301}, {**VALID, "reason_fa": 12},
            {**VALID, "doctor_summary_fa": "x" * 1201},
            {**VALID, "considerations_fa": ["x"] * 6},
            {**VALID, "considerations_fa": ["x" * 201]},
            {**VALID, "considerations_fa": [None]}, {},
        ]
        for index, value in enumerate(variants):
            with self.subTest(index=index):
                state = self.complete()
                with self.configured(), patch.object(llm, "chat_completion", return_value=value):
                    self.assert_fallback(self.client.post(self.endpoint(state)))

    def test_invalid_json_transport_timeout_and_http_failures_fall_back(self):
        for category in ("invalid_response", "transport_error", "http_error"):
            with self.subTest(category=category):
                state = self.complete()
                original_client = httpx.Client
                def handle(request):
                    if category == "transport_error":
                        raise httpx.ReadTimeout("synthetic timeout", request=request)
                    if category == "http_error":
                        return httpx.Response(503, text="synthetic provider error")
                    return httpx.Response(200, json={"choices": [{"message": {"content": "invalid JSON"}}]})
                def client(**kwargs):
                    return original_client(**{**kwargs, "transport": httpx.MockTransport(handle)})
                with self.configured(), patch.object(llm.httpx, "Client", side_effect=client):
                    self.assert_fallback(self.client.post(self.endpoint(state)))

    def test_emergency_urgency_has_no_doctors_and_fixed_notice(self):
        state = self.complete()
        with self.configured(), patch.object(llm, "chat_completion", return_value={**VALID, "urgency": "emergency"}):
            response = self.client.post(self.endpoint(state))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["emergency"])
        self.assertEqual(response.json()["doctors"], [])
        self.assertEqual(response.json()["notice"], EMERGENCY_REPLY)

    def test_failed_provider_fallback_is_replaced_on_successful_retry(self):
        state = self.complete()
        with self.configured(), patch.object(
            llm, "chat_completion", side_effect=[llm.LLMError("transport_error"), VALID]
        ) as call:
            self.assert_fallback(self.client.post(self.endpoint(state)))
            response = self.client.post(self.endpoint(state))
        self.assertEqual(call.call_count, 2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "llm")
        self.assertEqual(response.json()["specialty"]["code"], VALID["specialty_code"])
        self.assertEqual(response.json()["reason"], VALID["reason_fa"])
        with closing(db.connect()) as connection:
            rows = connection.execute("SELECT * FROM triage_results").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["session_id"], state["session_id"])
        self.assertEqual(rows[0]["source"], "llm")
        self.assertEqual(rows[0]["model"], "synthetic-model")
        self.assertEqual(rows[0]["doctor_summary_fa"], VALID["doctor_summary_fa"])
        self.assertEqual(json.loads(rows[0]["considerations_fa"]), VALID["considerations_fa"])

    def test_failed_retry_keeps_stored_fallback_unchanged(self):
        for outcome in (
            llm.LLMError("transport_error"), llm.LLMError("invalid_response"),
            {**VALID, "specialty_code": "invalid"},
        ):
            with self.subTest(outcome=type(outcome).__name__):
                state = self.complete()
                original = self.client.post(self.endpoint(state))
                with closing(db.connect()) as connection:
                    before = dict(connection.execute(
                        "SELECT * FROM triage_results WHERE session_id=?", (state["session_id"],)
                    ).fetchone())
                options = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
                with self.configured(), patch.object(llm, "chat_completion", **options) as call:
                    response = self.client.post(self.endpoint(state))
                call.assert_called_once()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), original.json())
                with closing(db.connect()) as connection:
                    after = dict(connection.execute(
                        "SELECT * FROM triage_results WHERE session_id=?", (state["session_id"],)
                    ).fetchone())
                self.assertEqual(after, before)

    def test_unconfigured_stored_fallback_makes_no_provider_call(self):
        state = self.complete()
        original = self.client.post(self.endpoint(state))
        with patch.object(llm, "chat_completion") as call:
            response = self.client.post(self.endpoint(state))
        call.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), original.json())

    def test_later_retry_cannot_overwrite_concurrent_llm_result(self):
        for late_outcome in ({**VALID, "specialty_code": "dermatology"}, llm.LLMError("transport_error")):
            with self.subTest(outcome=type(late_outcome).__name__):
                state = self.complete()
                self.assert_fallback(self.client.post(self.endpoint(state)))
                started = Event()
                release = Event()
                def delayed(settings, messages):
                    started.set()
                    if not release.wait(timeout=10):
                        raise AssertionError("Timed out waiting to finish the retry")
                    if isinstance(late_outcome, Exception):
                        raise late_outcome
                    return late_outcome
                with self.configured(), patch.object(llm, "chat_completion", side_effect=delayed):
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pending = pool.submit(triage.run_triage, state["session_id"])
                        try:
                            self.assertTrue(started.wait(timeout=10))
                            with patch.object(llm, "chat_completion", return_value=VALID):
                                winner = dict(triage.run_triage(state["session_id"]))
                        finally:
                            release.set()
                        late = dict(pending.result(timeout=10))
                self.assertEqual(winner["source"], "llm")
                self.assertEqual(late, winner)
                with closing(db.connect()) as connection:
                    rows = connection.execute(
                        "SELECT * FROM triage_results WHERE session_id=?", (state["session_id"],)
                    ).fetchall()
                self.assertEqual([dict(row) for row in rows], [winner])

    def test_repeated_call_reuses_stored_result(self):
        state = self.complete()
        with self.configured(), patch.object(llm, "chat_completion", return_value=VALID) as call:
            first = self.client.post(self.endpoint(state))
            second = self.client.post(self.endpoint(state))
        self.assertEqual(first.json(), second.json())
        call.assert_called_once()
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM triage_results").fetchone()[0], 1)

    def test_404_and_both_409_cases_do_not_call_provider(self):
        state = self.client.post("/v1/chat/sessions").json()
        with self.configured(), patch.object(llm, "chat_completion") as call:
            response = self.client.post("/v1/chat/sessions/unknown/triage")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {"error": {"code": "http_404", "message": "Not Found"}})
            response = self.client.post(self.endpoint(state))
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json(), {"error": {"code": "http_409", "message": "Conflict"}})
            path = f"/v1/chat/sessions/{state['session_id']}/messages"
            self.client.post(path, json={"message": "30"})
            self.client.post(path, json={"message": "chest pain"})
            self.assertEqual(self.client.post(self.endpoint(state)).status_code, 409)
        call.assert_not_called()

    def test_delete_patient_cascades_triage(self):
        state = self.complete()
        self.assert_fallback(self.client.post(self.endpoint(state)))
        self.assertEqual(self.client.delete("/v1/me").status_code, 204)
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM triage_results").fetchone()[0], 0)

    def test_no_transaction_or_connection_held_during_provider_call(self):
        for retry in (False, True):
            with self.subTest(retry=retry):
                state = self.complete()
                if retry:
                    self.assert_fallback(self.client.post(self.endpoint(state)))
                original_connect = db.connect
                opened = []
                def track():
                    connection = original_connect()
                    opened.append(connection)
                    return connection
                def complete(settings, messages):
                    self.assertTrue(opened)
                    for connection in opened:
                        with self.assertRaises(sqlite3.ProgrammingError):
                            connection.execute("SELECT 1")
                    with closing(original_connect()) as independent:
                        independent.execute("BEGIN IMMEDIATE")
                        independent.rollback()
                    return VALID
                with self.configured(), patch.object(db, "connect", side_effect=track), patch.object(llm, "chat_completion", side_effect=complete):
                    self.assertEqual(self.client.post(self.endpoint(state)).status_code, 200)

    def test_concurrent_results_return_the_same_stored_row(self):
        state = self.complete()
        barrier = Barrier(2)
        def complete(settings, messages):
            barrier.wait(timeout=10)
            return VALID
        with self.configured(), patch.object(llm, "chat_completion", side_effect=complete):
            with ThreadPoolExecutor(max_workers=2) as pool:
                rows = list(pool.map(lambda _: dict(triage.run_triage(state["session_id"])), range(2)))
        self.assertEqual(rows[0], rows[1])
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM triage_results").fetchone()[0], 1)

    def test_deletion_during_provider_call_does_not_recreate_data(self):
        state = self.complete()
        def complete(settings, messages):
            self.client.delete("/v1/me")
            return VALID
        with self.configured(), patch.object(llm, "chat_completion", side_effect=complete):
            self.assertEqual(self.client.post(self.endpoint(state)).status_code, 404)
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM triage_results").fetchone()[0], 0)

    def test_schema_v1_upgrade_preserves_existing_intake(self):
        state = self.complete()
        with closing(db.connect()) as connection, connection:
            connection.execute("DROP TABLE triage_results")
            connection.execute("PRAGMA user_version=1")
        with closing(db.connect()) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 5)
            self.assertEqual(connection.execute("SELECT age FROM sessions WHERE id=?", (state["session_id"],)).fetchone()[0], 30)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM triage_results").fetchone()[0], 0)

    def test_context_filters_orders_limits_caps_and_excludes_identifiers(self):
        visits = []
        patient_id = None
        for day in range(20, 25):
            state = self.complete(patient_id)
            patient_id = patient_of(state)
            visits.append(state)
            with closing(db.connect()) as connection, connection:
                connection.execute("UPDATE sessions SET created_at=? WHERE id=?", (f"2026-10-{day}T12:00:00+00:00", state["session_id"]))
        self.client.post(self.endpoint(visits[-1]))
        incomplete = self.create(patient_id)
        path = f"/v1/chat/sessions/{incomplete['session_id']}/messages"
        self.client.post(path, json={"message": "no"})
        for answer in ("30", "170", "70", "chest pain"):
            self.client.post(path, json={"message": answer})
        unfinished = self.create(patient_id)
        with closing(db.connect()) as connection, connection:
            for excluded in (incomplete, unfinished):
                connection.execute("UPDATE sessions SET created_at='2026-10-24T20:00:00+00:00' WHERE id=?", (excluded["session_id"],))
        other = self.complete()
        current = self.complete(patient_id)
        with closing(db.connect()) as connection, connection:
            connection.execute("UPDATE sessions SET created_at='2026-10-25T12:00:00+00:00' WHERE id=?", (current["session_id"],))
            for session in (current, visits[-1]):
                connection.execute(
                    "UPDATE sessions SET symptoms=?, duration=?, medications=?, allergies=? WHERE id=?",
                    ("x" * 700 + " cough", "d" * 750, "m" * 700 + " ibuprofen", "a" * 750, session["session_id"]),
                )
            context = build_context(connection, current["session_id"])
        self.assertEqual([visit["date"] for visit in context["previous_visits"]], ["2026-10-24", "2026-10-23", "2026-10-22"])
        self.assertEqual(context["previous_visits"][0]["triage_specialty"], "general_practice")
        self.assertIsNone(context["previous_visits"][1]["triage_specialty"])
        for name in ("symptoms", "duration", "medications", "allergies"):
            self.assertEqual(len(context["current"][name]), 500)
            self.assertEqual(len(context["previous_visits"][0][name]), 500)
        self.assertEqual(context["current"]["matched"]["symptoms"], ["سرفه"])
        self.assertEqual(len(context["current"]["matched"]["medicines"]), 1)
        serialized = json.dumps(context)
        for session in visits + [current, other, incomplete]:
            self.assertNotIn(session["session_id"], serialized)
            self.assertNotIn(patient_of(session), serialized)
        for forbidden in ("patient_id", "session_id", "created_at", "messages", "doctor_summary_fa", "considerations_fa"):
            self.assertNotIn(forbidden, serialized)
        with closing(db.connect()) as connection:
            with self.assertRaises(KeyError):
                build_context(connection, "unknown")
