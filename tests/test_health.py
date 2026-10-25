import os
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


class HealthTests(unittest.TestCase):
    def test_health(self):
        with TestClient(app) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_settings_defaults_and_environment(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Settings().log_level, "INFO")
        with patch.dict(os.environ, {"APP_LOG_LEVEL": "warning"}):
            settings = Settings()
            self.assertEqual(settings.log_level, "WARNING")
        with self.assertRaises(FrozenInstanceError):
            settings.log_level = "ERROR"
        with patch.dict(os.environ, {"APP_LOG_LEVEL": "invalid"}):
            with self.assertRaises(ValueError):
                Settings()