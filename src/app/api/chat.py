import sqlite3
from contextlib import closing
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agent import sessions, triage
from app.api.deps import no_body, owned_session, patient_user
from app.schemas.chat import ChatResponse, ConversationDetail, ConversationItem, MessageRequest
from app.schemas.common import ErrorResponse
from app.schemas.triage import TriageResponse
from app.core import db
from app.services import visits

router = APIRouter(prefix="/v1/chat", tags=["chat"], responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}})


def _response(row: sqlite3.Row) -> ChatResponse:
    state = sessions.restore(row)
    return ChatResponse(
        session_id=row["id"], returning=bool(row["returning"]),
        reply=state.reply, step=state.step, done=state.done, emergency=state.emergency,
        collected=state.collected,
    )


@router.post("/sessions", status_code=201, response_model=ChatResponse, dependencies=[Depends(no_body)], responses={422: {"model": ErrorResponse}})
def create_chat_session(user: dict = Depends(patient_user)) -> ChatResponse:
    return _response(sessions.create_session(user["patient_id"]))


@router.get("/sessions", response_model=list[ConversationItem], responses={422: {"model": ErrorResponse}})
def conversations(limit: Annotated[int, Query(ge=1, le=50)] = 20, user: dict = Depends(patient_user)) -> list[dict]:
    return sessions.list_sessions(user["patient_id"], limit)


@router.get("/sessions/{session_id}", response_model=ConversationDetail, responses={404: {"model": ErrorResponse}})
def conversation(session_id: str, user: dict = Depends(owned_session)) -> dict:
    with closing(db.connect()) as connection, connection:
        connection.execute("BEGIN")
        row = connection.execute("SELECT * FROM sessions WHERE id=? AND patient_id=?", (session_id, user["patient_id"])).fetchone()
        if row is None:
            raise HTTPException(status_code=404)
        stored = connection.execute("SELECT * FROM triage_results WHERE session_id=?", (session_id,)).fetchone()
        request = connection.execute("SELECT * FROM visit_requests WHERE session_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1", (session_id,)).fetchone()
        return {"session": _response(sessions._read(connection, session_id)),
                "transcript": [dict(message) for message in connection.execute(
                    "SELECT role,content,created_at FROM messages WHERE session_id=? ORDER BY id LIMIT 200", (session_id,))],
                "triage": triage.patient_response(stored) if stored is not None else None,
                "request": visits._patient_item(connection, request) if request is not None else None}


@router.post("/sessions/{session_id}/messages", response_model=ChatResponse, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
def chat_message(session_id: str, body: MessageRequest, user: dict = Depends(owned_session)) -> ChatResponse:
    try:
        return _response(sessions.send_message(session_id, body.message, body.edit_field))
    except KeyError:
        raise HTTPException(status_code=404) from None


@router.post("/sessions/{session_id}/triage", response_model=TriageResponse, responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
def session_triage(session_id: str, user: dict = Depends(owned_session)) -> dict:
    try:
        return triage.patient_response(triage.run_triage(session_id))
    except KeyError:
        raise HTTPException(status_code=404) from None
    except triage.IntakeNotReady:
        raise HTTPException(status_code=409) from None
