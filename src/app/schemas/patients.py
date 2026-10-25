from typing import Literal

from pydantic import BaseModel

from app.agent.intake import Collected
from app.schemas.chat import Matched


class HistoryMessage(BaseModel):
    role: Literal["user", "bot"]
    content: str
    created_at: str


class HistoryVisit(BaseModel):
    session_id: str
    created_at: str
    done: bool
    emergency: bool
    collected: Collected
    matched: Matched
    messages: list[HistoryMessage]
