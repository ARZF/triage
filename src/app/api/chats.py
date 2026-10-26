from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import current_user, verified_doctor
from app.schemas.chats import EndResponse, MessagePage, MessageRequest, VisitMessage
from app.schemas.common import ErrorResponse
from app.services import chats

router = APIRouter(prefix="/v1/visit-requests", tags=["visit chat"], responses={
    status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 422)
})


@router.get("/{request_id}/messages", response_model=MessagePage)
def messages(request_id: str, after: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
             limit: Annotated[int, Query(ge=1, le=100)] = 50, user: dict = Depends(current_user)) -> dict:
    return chats.read_messages(request_id, user, after, limit)


@router.post("/{request_id}/messages", status_code=201, response_model=VisitMessage)
def send_message(request_id: str, body: MessageRequest, user: dict = Depends(current_user)) -> dict:
    return chats.post_message(request_id, user, body.content)


@router.post("/{request_id}/end", response_model=EndResponse)
def end(request_id: str, user: dict = Depends(verified_doctor)) -> dict:
    return chats.end_visit(request_id, user)
