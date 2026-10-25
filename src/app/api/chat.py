import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.agent import sessions, triage
from app.api.deps import no_body, owned_session, patient_user
from app.schemas.chat import ChatResponse, MessageRequest
from app.schemas.common import ErrorResponse
from app.schemas.triage import TriageResponse

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


@router.post("/sessions/{session_id}/messages", response_model=ChatResponse, responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
def chat_message(session_id: str, body: MessageRequest, user: dict = Depends(owned_session)) -> ChatResponse:
    try:
        return _response(sessions.send_message(session_id, body.message))
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
