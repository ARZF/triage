from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SpecialtyCode = Literal[
    "general_practice", "internal_medicine", "pediatrics", "ent", "dermatology",
    "gastroenterology", "neurology", "cardiology", "pulmonology",
]
Urgency = Literal["routine", "soon", "urgent", "emergency"]


class LLMResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    specialty_code: SpecialtyCode
    urgency: Urgency
    reason_fa: str = Field(max_length=300)
    doctor_summary_fa: str = Field(max_length=1200)
    considerations_fa: list[Annotated[str, Field(max_length=200)]] = Field(max_length=5)


class Specialty(BaseModel):
    code: SpecialtyCode
    name_fa: str


class Doctor(BaseModel):
    id: str
    name_fa: str
    expertise: list[str]
    score: float | None
    online: bool


class TriageResponse(BaseModel):
    session_id: str
    source: Literal["llm", "fallback"]
    specialty: Specialty
    urgency: Literal["routine", "soon", "urgent", "emergency", "unknown"]
    emergency: bool
    reason: str | None
    notice: str
    doctors: list[Doctor]
