from typing import Literal

from pydantic import BaseModel, Field, computed_field

from app.agent.dictionaries import match
from app.agent.intake import AnswerField, Collected, Step
from app.schemas.dictionaries import MatchedEntry
from app.schemas.triage import Specialty, TriageResponse
from app.schemas.visits import PatientVisit


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


class ConversationItem(BaseModel):
    session_id: str
    created_at: str
    summary: str | None
    step: Step
    done: bool
    emergency: bool
    status: Literal["intake", "triage", "pending", "accepted", "ended", "expired", "cancelled", "emergency"]
    specialty: Specialty | None
    request_id: str | None


class TranscriptMessage(BaseModel):
    role: Literal["user", "bot"]
    content: str
    created_at: str


class ConversationDetail(BaseModel):
    session: ChatResponse
    transcript: list[TranscriptMessage]
    triage: TriageResponse | None
    request: PatientVisit | None
