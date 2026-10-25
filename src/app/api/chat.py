import sqlite3

from fastapi import APIRouter, HTTPException

from app.agent import sessions
from app.schemas.chat import ChatResponse, MessageRequest, SessionRequest
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/v1/chat", tags=["chat"])


def _response(row: sqlite3.Row) -> ChatResponse:
    state = sessions.restore(row)
    return ChatResponse(
        session_id=row["id"], patient_id=row["patient_id"], returning=bool(row["returning"]),
        reply=state.reply, step=state.step, done=state.done, emergency=state.emergency,
        collected=state.collected,
    )


@router.post("/sessions", status_code=201, response_model=ChatResponse, responses={404: {"model": ErrorResponse}})
def create_chat_session(body: SessionRequest | None = None) -> ChatResponse:
    try:
        return _response(sessions.create_session(body.patient_id if body else None))
    except KeyError:
        raise HTTPException(status_code=404) from None


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def chat_message(session_id: str, body: MessageRequest) -> ChatResponse:
    try:
        return _response(sessions.send_message(session_id, body.message))
    except KeyError:
        raise HTTPException(status_code=404) from None
