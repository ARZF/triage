from pydantic import BaseModel, Field

from app.agent.intake import Collected, Step


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    step: Step
    done: bool
    emergency: bool
    collected: Collected
