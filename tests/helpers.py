from contextlib import closing
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
    })
    assert response.status_code == 201, response.text
    with closing(db.connect()) as connection:
        return dict(connection.execute(
            "SELECT d.* FROM doctors d JOIN users u ON u.id=d.user_id WHERE u.username=?", (username,)
        ).fetchone())
