import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.agent.doctor_assistant import CodexChat, release, reserve
from app.api.deps import verified_doctor
from app.core.config import Settings
from app.schemas.assistant import AssistantRequest
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/v1/doctor/assistant", tags=["doctor assistant"], responses={
    status: {"model": ErrorResponse} for status in (401, 403, 422, 429, 503, 504)})


@router.post("/messages", response_class=StreamingResponse, responses={200: {"content": {"text/event-stream": {}}}})
async def messages(body: AssistantRequest, user: dict = Depends(verified_doctor)):
    doctor_id = user["doctor_id"]
    reserve(doctor_id)
    chat = CodexChat()
    try:
        await chat.start([message.model_dump() for message in body.messages], Settings())
    except BaseException:
        release(doctor_id)
        raise

    async def cleanup():
        try:
            await chat.close()
        finally:
            release(doctor_id)

    async def stream():
        try:
            async for event, value in chat.events():
                yield f"event: {event}\ndata: {json.dumps(value, ensure_ascii=False)}\n\n"
        finally:
            await cleanup()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"},
                             background=BackgroundTask(cleanup))
