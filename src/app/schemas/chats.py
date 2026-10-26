from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class VisitMessage(BaseModel):
    id: int
    sender: Literal["patient", "doctor"]
    content: str
    created_at: str


class MessagePage(BaseModel):
    messages: list[VisitMessage]
    ended: bool
    has_more: bool


class EndResponse(BaseModel):
    ended: Literal[True] = True
