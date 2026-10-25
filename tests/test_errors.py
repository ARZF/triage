import unittest

from fastapi import Body, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.common import ErrorResponse


class ErrorTests(unittest.TestCase):
    def test_unknown_path(self):
        with TestClient(app) as client:
            response = client.get("/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"error": {"code": "http_404", "message": "Not Found"}},
        )
        ErrorResponse.model_validate(response.json())

    def test_validation_does_not_echo_input(self):
        test_app = FastAPI(exception_handlers=app.exception_handlers)

        @test_app.post("/test-only")
        def validate(count: int = Body(embed=True)):
            return {"count": count}

        with TestClient(test_app) as client:
            response = client.post(
                "/test-only", json={"count": "synthetic-private-input"}
            )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                }
            },
        )
        ErrorResponse.model_validate(response.json())
        self.assertNotIn("synthetic-private-input", response.text)
        self.assertNotIn("/test-only", app.openapi()["paths"])

    def test_http_error_does_not_echo_detail(self):
        test_app = FastAPI(exception_handlers=app.exception_handlers)

        @test_app.get("/test-only")
        def fail():
            raise HTTPException(status_code=400, detail="synthetic-private-detail")

        with TestClient(test_app) as client:
            response = client.get("/test-only")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"error": {"code": "http_400", "message": "Bad Request"}},
        )
        self.assertNotIn("synthetic-private-detail", response.text)