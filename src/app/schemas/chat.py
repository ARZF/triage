from pydantic import BaseModel, Field, computed_field

from app.agent.dictionaries import match
from app.agent.intake import AnswerField, Collected, Step
from app.schemas.dictionaries import MatchedEntry


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    edit_field: AnswerField | None = None


class Matched(BaseModel):
    symptoms: list[MatchedEntry]
    medicines: list[MatchedEntry]


class ChatResponse(BaseModel):
    session_id: str
    returning: bool
    reply: str
    step: Step
    done: bool
    emergency: bool
    collected: Collected

    @computed_field
    @property
    def matched(self) -> Matched:
        return Matched(
            symptoms=match("symptoms", self.collected.symptoms or ""),
            medicines=match("medicines", self.collected.medications or ""),
        )
