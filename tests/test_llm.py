import json
import os
import unittest
from unittest.mock import patch

import httpx

from app.core.config import Settings
from app.core.llm import LLMError, chat_completion


class LLMConfigTests(unittest.TestCase):
    def test_defaults_optional_configuration_and_secret_repr(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            self.assertEqual(settings.llm_timeout_seconds, 30)
            self.assertFalse(settings.llm_configured)
            self.assertFalse(Settings(llm_base_url="http://localhost:8001/v1").llm_configured)
            configured = Settings(
                llm_base_url="https://example.test/v1", llm_model="synthetic-model",
                llm_api_key="synthetic-secret-key",
            )
            self.assertTrue(configured.llm_configured)
            self.assertNotIn("synthetic-secret-key", repr(configured))
            self.assertNotIn("llm_api_key", repr(configured))

    def test_invalid_urls_name_only_the_variable(self):
        for url in (
            "not-a-url", "ftp://example.test/v1", "https://", "https://example.test:bad",
            "https://example.test:0", "https://example.test/with space",
            "https://secret:password@example.test/v1", "https://example.test?key=secret",
            "https://example.test/#secret", "https://example.test/\nsecret",
        ):
            with self.subTest(url=url), patch.dict(os.environ, {"APP_LLM_BASE_URL": url}):
                with self.assertRaises(ValueError) as error:
                    Settings()
                self.assertEqual(str(error.exception), "APP_LLM_BASE_URL")

    def test_timeout_bounds_and_invalid_optional_fields(self):
        for value in ("0", "0.9", "121", "nan", "inf", "-inf", "invalid", ""):
            with self.subTest(value=value), patch.dict(os.environ, {"APP_LLM_TIMEOUT_SECONDS": value}):
                with self.assertRaisesRegex(ValueError, "^APP_LLM_TIMEOUT_SECONDS$"):
                    Settings()
        for value in ("1", "120", "2.5"):
            with patch.dict(os.environ, {"APP_LLM_TIMEOUT_SECONDS": value}):
                self.assertEqual(Settings().llm_timeout_seconds, float(value))
        for variable in ("APP_LLM_MODEL", "APP_LLM_API_KEY"):
            with patch.dict(os.environ, {variable: "private\nvalue"}):
                with self.assertRaises(ValueError) as error:
                    Settings()
                self.assertEqual(str(error.exception), variable)


class LLMClientTests(unittest.TestCase):
    def settings(self, key=None):
        return Settings(
            llm_base_url="https://provider.test/v1/", llm_model="synthetic-model",
            llm_api_key=key, llm_timeout_seconds=17,
        )

    def test_url_auth_body_timeout_and_parsed_object(self):
        messages = [{"role": "system", "content": "Return JSON."}, {"role": "user", "content": "synthetic"}]
        for key in (None, "synthetic-secret"):
            with self.subTest(key_present=bool(key)):
                def handle(request):
                    self.assertEqual(str(request.url), "https://provider.test/v1/chat/completions")
                    self.assertEqual(request.method, "POST")
                    if key:
                        self.assertEqual(request.headers["Authorization"], "Bearer " + key)
                    else:
                        self.assertNotIn("authorization", request.headers)
                    self.assertEqual(json.loads(request.content), {
                        "model": "synthetic-model", "messages": messages, "temperature": 0,
                        "response_format": {"type": "json_object"},
                    })
                    self.assertTrue(all(value == 17 for value in request.extensions["timeout"].values()))
                    return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})
                result = chat_completion(self.settings(key), messages, transport=httpx.MockTransport(handle))
                self.assertEqual(result, {"ok": True})

    def test_non_2xx_bad_envelopes_and_non_json_content(self):
        responses = [
            httpx.Response(401, text="private provider text"),
            httpx.Response(503, text="private provider text"),
            httpx.Response(200, text="private provider text"),
            httpx.Response(200, json={}),
            httpx.Response(200, json={"choices": []}),
        ] + [
            httpx.Response(200, json={"choices": [{"message": {"content": value}}]})
            for value in ("not JSON", "[]", "null", 123, {}, None)
        ]
        for response in responses:
            with self.subTest(status=response.status_code):
                with self.assertLogs("app.core.llm", level="WARNING") as logs:
                    with self.assertRaises(LLMError):
                        chat_completion(
                            self.settings("synthetic-secret"), [],
                            transport=httpx.MockTransport(lambda request: response),
                        )
                self.assertNotIn("private provider text", str(logs.output))
                self.assertNotIn("synthetic-secret", str(logs.output))
                self.assertNotIn("provider.test", str(logs.output))

    def test_transport_timeout_uses_safe_error_and_logs(self):
        def timeout(request):
            raise httpx.ReadTimeout("private prompt and synthetic-secret", request=request)
        with self.assertLogs("app.core.llm", level="WARNING") as logs:
            with self.assertRaisesRegex(LLMError, "^transport_error$"):
                chat_completion(self.settings(), [], transport=httpx.MockTransport(timeout))
        self.assertEqual(logs.output, ["WARNING:app.core.llm:transport_error"])
