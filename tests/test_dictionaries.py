import tempfile
import os
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agent import dictionaries
from app.main import app
from helpers import as_patient, patient_of, register_patient


class DictionaryTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "test.db"
        self.enterContext(patch.dict(os.environ, {"APP_DB_PATH": str(self.db_path)}))
        self.document = {
            "status": dictionaries.STATUS,
            "entries": [{
                "code": "synthetic", "name_fa": "نمونه", "name_en": "synthetic",
                "aliases": ["synthetic"],
            }],
        }

    def test_both_files_load_with_twelve_entries(self):
        loaded = dictionaries.load_dictionaries()
        self.assertEqual(set(loaded), {"symptoms", "medicines"})
        for kind, entries in loaded.items():
            with self.subTest(kind=kind):
                self.assertEqual(len(entries), 12)
                self.assertEqual(len({entry["code"] for entry in entries}), 12)

    def test_startup_cache_reads_each_file_only_once(self):
        dictionaries.load_dictionaries.cache_clear()
        self.addCleanup(dictionaries.load_dictionaries.cache_clear)
        with patch.object(dictionaries, "load_file", wraps=dictionaries.load_file) as read:
            first = dictionaries.load_dictionaries()
            second = dictionaries.load_dictionaries()
            self.assertIs(first, second)
            self.assertEqual(read.call_count, 2)
            with TestClient(app):
                pass
            self.assertEqual(read.call_count, 2)

    def test_invalid_documents_raise_sanitized_value_error(self):
        for document in (
            [], {}, {"status": dictionaries.STATUS, "entries": None},
            {"status": "sensitive-document-marker", "entries": []},
        ):
            with self.subTest(document_type=type(document).__name__):
                with patch.object(Path, "read_text", return_value=json.dumps(document)):
                    with self.assertRaisesRegex(ValueError, r"symptoms\.json: code") as caught:
                        dictionaries.load_file(Path("symptoms.json"))
                self.assertNotIn("sensitive-document-marker", str(caught.exception))

    def test_every_entry_validation_failure(self):
        failures = (
            {"code": None}, {"code": 12}, {"code": ""}, {"code": "Bad-Code"},
            {"name_fa": ""}, {"name_fa": " "}, {"name_fa": None},
            {"name_en": ""}, {"name_en": 12},
            {"aliases": None}, {"aliases": "sensitive-alias-marker"},
            {"aliases": [""]}, {"aliases": [" "]}, {"aliases": [12]},
            {"aliases": ["valid", None]},
        )
        for change in failures:
            with self.subTest(field=next(iter(change))):
                document = copy.deepcopy(self.document)
                document["entries"][0].update(change)
                with patch.object(Path, "read_text", return_value=json.dumps(document)):
                    with self.assertRaisesRegex(ValueError, r"symptoms\.json: code") as caught:
                        dictionaries.load_file(Path("symptoms.json"))
                self.assertNotIn("sensitive-alias-marker", str(caught.exception))
                if "code" not in change:
                    self.assertIn("synthetic", str(caught.exception))
        for entry in ({}, "sensitive-entry-marker"):
            document = {"status": dictionaries.STATUS, "entries": [entry]}
            with patch.object(Path, "read_text", return_value=json.dumps(document)):
                with self.assertRaisesRegex(ValueError, r"symptoms\.json: code"):
                    dictionaries.load_file(Path("symptoms.json"))

    def test_duplicate_codes_are_rejected(self):
        self.document["entries"] *= 2
        with patch.object(Path, "read_text", return_value=json.dumps(self.document)):
            with self.assertRaisesRegex(ValueError, r"symptoms\.json: code 'synthetic': duplicate"):
                dictionaries.load_file(Path("symptoms.json"))

    def test_unreadable_invalid_json_and_encoding_are_sanitized(self):
        for error in (
            FileNotFoundError("sensitive-file-marker"),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "sensitive-file-marker"),
        ):
            with self.subTest(error=type(error).__name__):
                with patch.object(Path, "read_text", side_effect=error):
                    with self.assertRaisesRegex(ValueError, r"symptoms\.json: code") as caught:
                        dictionaries.load_file(Path("symptoms.json"))
                self.assertNotIn("sensitive-file-marker", str(caught.exception))
        with patch.object(Path, "read_text", return_value="sensitive-json-marker{"):
            with self.assertRaisesRegex(ValueError, r"symptoms\.json: code") as caught:
                dictionaries.load_file(Path("symptoms.json"))
        self.assertNotIn("sensitive-json-marker", str(caught.exception))

    def test_invalid_dictionary_stops_startup(self):
        dictionaries.load_dictionaries.cache_clear()
        self.addCleanup(dictionaries.load_dictionaries.cache_clear)
        with patch.object(
            dictionaries, "load_file", side_effect=ValueError("symptoms.json: code bad: invalid")
        ):
            with self.assertRaisesRegex(ValueError, "symptoms.json"):
                with TestClient(app):
                    self.fail("Application started with invalid vocabulary")

    def test_normalization(self):
        self.assertEqual(
            dictionaries.normalize("  ك ي‌۳،٤؛۵.٦!۷? "),
            "ک ی 3 4 5 6 7",
        )

    def test_matching_words_phrases_order_variants_and_deduplication(self):
        cases = (
            ("symptoms", "سرفه و تب خفیف", ["cough", "fever"]),
            ("symptoms", "تب و سرفه", ["fever", "cough"]),
            ("symptoms", "تبریز و coughing", []),
            ("symptoms", "درد شكمي", ["abdominal_pain"]),
            ("symptoms", "سر‌درد و سر درد", ["headache"]),
            ("medicines", "آموكسي سيلين", ["amoxicillin"]),
            ("medicines", "آموکسی‌سیلین و آموکسیسیلین", ["amoxicillin"]),
            ("symptoms", "۱۲،سرفه؛٣؟تب!", ["cough", "fever"]),
            ("symptoms", "HEADACHE; cough!", ["headache", "cough"]),
            ("symptoms", "headache و سردرد، سر درد", ["headache"]),
            ("symptoms", "skin-rash", ["skin_rash"]),
            ("medicines", "PARACETAMOL, acetaminophen", ["acetaminophen"]),
            ("medicines", "هیچ", []),
            ("symptoms", "", []),
        )
        for kind, text, expected in cases:
            with self.subTest(kind=kind, text=text):
                self.assertEqual(
                    [entry["code"] for entry in dictionaries.match(kind, text)], expected
                )

    def test_persian_name_is_implicit_alias(self):
        with patch.object(dictionaries, "load_dictionaries", return_value={
            "symptoms": self.document["entries"]
        }):
            self.assertEqual(dictionaries.match("symptoms", "نمونه")[0]["code"], "synthetic")


class DictionaryApiTests(unittest.TestCase):
    def setUp(self):
        self.db_path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "test.db"
        self.enterContext(patch.dict(os.environ, {"APP_DB_PATH": str(self.db_path)}))
        self.client = self.enterContext(TestClient(app))
        self.user = register_patient(self.client)

    def test_dictionary_endpoint_without_query_and_with_limit(self):
        for kind in ("symptoms", "medicines"):
            with self.subTest(kind=kind):
                response = self.client.get(f"/v1/dictionaries/{kind}")
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(set(body), {"kind", "entries"})
                self.assertEqual(body["kind"], kind)
                self.assertEqual(len(body["entries"]), 12)
                self.assertEqual(set(body["entries"][0]), {"code", "name_fa", "name_en", "aliases"})
        for limit, expected in ((1, 1), (100, 12)):
            response = self.client.get("/v1/dictionaries/symptoms", params={"limit": limit})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["entries"]), expected)

    def test_dictionary_query_is_normalized_substring_search(self):
        for kind, q, expected in (
            ("symptoms", "رف", ["cough"]),
            ("medicines", "PARACE", ["acetaminophen"]),
            ("medicines", "آموكسي‌سيلين", ["amoxicillin"]),
            ("symptoms", "not-a-known-vocabulary", []),
        ):
            with self.subTest(kind=kind, q=q):
                response = self.client.get(f"/v1/dictionaries/{kind}", params={"q": q})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([e["code"] for e in response.json()["entries"]], expected)
        response = self.client.get("/v1/dictionaries/symptoms", params={"q": "", "limit": 2})
        self.assertEqual(len(response.json()["entries"]), 2)
        response = self.client.get("/v1/dictionaries/symptoms", params={"q": " " * 100})
        self.assertEqual(response.status_code, 200)

    def test_invalid_kind_query_and_limits_return_error_response(self):
        for path, params in (
            ("/v1/dictionaries/unknown", {}),
            ("/v1/dictionaries/symptoms", {"limit": 0}),
            ("/v1/dictionaries/symptoms", {"limit": 101}),
            ("/v1/dictionaries/symptoms", {"limit": "bad"}),
            ("/v1/dictionaries/symptoms", {"q": "x" * 101}),
        ):
            with self.subTest(path=path, params=params):
                response = self.client.get(path, params=params)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(), {
                    "error": {"code": "validation_error", "message": "Request validation failed"}
                })

    def test_full_intake_matches_symptoms_and_no_medicine(self):
        created = self.client.post("/v1/chat/sessions")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["matched"], {"symptoms": [], "medicines": []})
        path = "/v1/chat/sessions/" + created.json()["session_id"] + "/messages"
        for answer in ("۳۰", "سرفه و تب خفیف", "دو روز", "۳", "هیچ", "ندارد", "بله"):
            response = self.client.post(path, json={"message": answer})
            self.assertEqual(response.status_code, 200)
        state = response.json()
        self.assertTrue(state["done"])
        self.assertEqual(state["matched"], {
            "symptoms": [{"code": "cough", "name_fa": "سرفه"}, {"code": "fever", "name_fa": "تب"}],
            "medicines": [],
        })
        self.assertEqual(self.client.post(path, json={"message": "خیر"}).json(), state)

    def test_medicine_matches_and_reset_clear_matches(self):
        session_id = self.client.post("/v1/chat/sessions").json()["session_id"]
        path = f"/v1/chat/sessions/{session_id}/messages"
        for answer in ("30", "cough", "two days", "3", "استامینوفن و ibuprofen"):
            response = self.client.post(path, json={"message": answer})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [entry["code"] for entry in response.json()["matched"]["medicines"]],
            ["acetaminophen", "ibuprofen"],
        )
        self.client.post(path, json={"message": "none"})
        response = self.client.post(path, json={"message": "no"})
        self.assertEqual(response.json()["matched"], {"symptoms": [], "medicines": []})

    def test_red_flag_answer_produces_no_symptom_matches(self):
        session_id = self.client.post("/v1/chat/sessions").json()["session_id"]
        path = f"/v1/chat/sessions/{session_id}/messages"
        self.client.post(path, json={"message": "30"})
        response = self.client.post(path, json={"message": "سرفه و درد سینه"})
        state = response.json()
        self.assertTrue(state["emergency"])
        self.assertIsNone(state["collected"]["symptoms"])
        self.assertEqual(state["matched"]["symptoms"], [])

    def test_each_default_symptom_name_is_a_valid_matching_answer(self):
        entries = self.client.get("/v1/dictionaries/symptoms", params={"limit": 100}).json()["entries"]
        for entry in entries:
            with self.subTest(code=entry["code"]):
                session_id = self.client.post("/v1/chat/sessions").json()["session_id"]
                path = f"/v1/chat/sessions/{session_id}/messages"
                self.client.post(path, json={"message": "30"})
                response = self.client.post(path, json={"message": entry["name_fa"]})
                self.assertEqual(response.status_code, 200)
                state = response.json()
                self.assertEqual(state["step"], "duration")
                self.assertEqual(state["collected"]["symptoms"], entry["name_fa"])
                self.assertIn(entry["code"], [match["code"] for match in state["matched"]["symptoms"]])

    def test_each_default_medicine_name_is_a_valid_matching_answer(self):
        entries = self.client.get("/v1/dictionaries/medicines", params={"limit": 100}).json()["entries"]
        for entry in entries:
            with self.subTest(code=entry["code"]):
                session_id = self.client.post("/v1/chat/sessions").json()["session_id"]
                path = f"/v1/chat/sessions/{session_id}/messages"
                for answer in ("30", "cough", "two days", "3"):
                    self.client.post(path, json={"message": answer})
                response = self.client.post(path, json={"message": entry["name_fa"]})
                self.assertEqual(response.status_code, 200)
                state = response.json()
                self.assertEqual(state["step"], "allergies")
                self.assertEqual(state["collected"]["medications"], entry["name_fa"])
                self.assertIn(entry["code"], [match["code"] for match in state["matched"]["medicines"]])

    def test_multi_medicine_answer_is_preserved_and_matched(self):
        names = self.client.get("/v1/dictionaries/medicines").json()["entries"][:2]
        medications = "، ".join([entry["name_fa"] for entry in names] + ["نام ساختگی نامرتبط"])
        session_id = self.client.post("/v1/chat/sessions").json()["session_id"]
        path = f"/v1/chat/sessions/{session_id}/messages"
        for answer in ("30", "cough", "two days", "3", medications, "none", "yes"):
            response = self.client.post(path, json={"message": answer})
            self.assertEqual(response.status_code, 200)
        state = response.json()
        self.assertTrue(state["done"])
        self.assertEqual(state["collected"]["medications"], medications)
        self.assertEqual(
            [entry["code"] for entry in state["matched"]["medicines"]],
            [entry["code"] for entry in names],
        )
