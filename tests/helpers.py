from contextlib import closing
from contextlib import contextmanager
import os
from unittest.mock import patch
from uuid import uuid4

from app.core import db

PASSWORD = "synthetic-password"


def intake_answers(age="30", symptoms="cough", duration="two days", severity="3", medications="none", allergies="none", confirm="yes", additional_context="رد کردن"):
    return (age, "170.5", "70.2", "synthetic complaint", symptoms, duration, severity,
            "none", medications, "none", "none", allergies, additional_context, confirm)


def register_patient(client):
    username = "patient_" + uuid4().hex[:12]
    response = client.post("/v1/auth/register", json={
        "role": "patient", "username": username, "password": PASSWORD,
    })
    assert response.status_code == 201, response.text
    assert client.post("/v1/auth/logout").status_code == 204
    response = client.post("/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    with closing(db.connect()) as connection:
        return dict(connection.execute("SELECT id, patient_id, username FROM users WHERE username=?", (username,)).fetchone())


def as_patient(client, patient_id):
    with closing(db.connect()) as connection:
        user = connection.execute("SELECT username FROM users WHERE patient_id=?", (patient_id,)).fetchone()
    assert user is not None
    response = client.post("/v1/auth/login", json={"username": user["username"], "password": PASSWORD})
    assert response.status_code == 200, response.text


def patient_of(state):
    with closing(db.connect()) as connection:
        return connection.execute("SELECT patient_id FROM sessions WHERE id=?", (state["session_id"],)).fetchone()[0]


def register_doctor(client, specialty="general_practice", username=None):
    username = username or "doctor_" + uuid4().hex[:12]
    response = client.post("/v1/auth/register", json={
        "role": "doctor", "username": username, "password": PASSWORD,
        "name_fa": "پزشک فرضی آزمایشی", "specialty_code": specialty,
        "expertise": ["مرور اطلاعات", "گفت‌وگوی اولیه"],
        "license_number": "DEMO-" + uuid4().hex[:15],
    })
    assert response.status_code == 201, response.text
    with closing(db.connect()) as connection:
        return dict(connection.execute(
            "SELECT d.* FROM doctors d JOIN users u ON u.id=d.user_id WHERE u.username=?", (username,)
        ).fetchone())


@contextmanager
def admin_account(client):
    from app.services.admin import seed_admin
    with patch.dict(os.environ, {"APP_ADMIN_USERNAME": "admin_demo", "APP_ADMIN_PASSWORD": PASSWORD}):
        seed_admin()
        response = client.post("/v1/auth/login", json={"username": "admin_demo", "password": PASSWORD})
        assert response.status_code == 200, response.text
        yield response.json()["user"]


def approve_doctor(admin_client, doctor_id):
    response = admin_client.post(f"/v1/admin/doctors/{doctor_id}/approve")
    assert response.status_code == 200, response.text
    return response.json()
