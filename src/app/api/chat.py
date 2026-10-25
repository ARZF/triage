from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.agent import sessions
from app.schemas.chat import ChatResponse, MessageRequest
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/v1/chat", tags=["chat"])


@router.post("/sessions", status_code=201, response_model=ChatResponse)
async def create_chat_session() -> ChatResponse:
    session_id, state = sessions.create_session()
    return ChatResponse(session_id=session_id, **asdict(state))


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def chat_message(session_id: str, body: MessageRequest) -> ChatResponse:
    try:
        state = sessions.send_message(session_id, body.message)
    except KeyError:
        raise HTTPException(status_code=404) from None
    return ChatResponse(session_id=session_id, **asdict(state))
