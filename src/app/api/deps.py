from contextlib import closing

from fastapi import Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from app.core import db
from app.services import accounts


def current_user(request: Request) -> dict:
    user = accounts.current_user(request.cookies.get("session"))
    if user is None:
        raise HTTPException(status_code=401)
    return user


def patient_user(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "patient":
        raise HTTPException(status_code=403)
    return user


def verified_doctor(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "doctor" or not user["verified"]:
        raise HTTPException(status_code=403)
    return user


def owned_session(session_id: str, user: dict = Depends(patient_user)) -> dict:
    with closing(db.connect()) as connection:
        row = connection.execute(
            "SELECT 1 FROM sessions WHERE id=? AND patient_id=?", (session_id, user["patient_id"])
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404)
    return user


async def no_body(request: Request) -> None:
    if await request.body():
        raise RequestValidationError([{"type": "extra_forbidden", "loc": ("body",), "msg": "Request body is not allowed"}])
