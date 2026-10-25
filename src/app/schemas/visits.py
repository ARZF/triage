from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.schemas.triage import Specialty


class VisitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(min_length=1, max_length=64)


class Availability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available: StrictBool


class VisitDoctor(BaseModel):
    id: str
    name_fa: str
    expertise: list[str]
    score: float | None


class PatientVisit(BaseModel):
    id: str
    status: Literal["pending", "accepted", "cancelled", "expired"]
    created_at: str
    specialty: Specialty
    doctor: VisitDoctor | None


class Preview(BaseModel):
    age: int | None
    symptoms: str | None
    duration: str | None
    severity: int | None


class MatchedNames(BaseModel):
    symptoms: list[str]
    medicines: list[str]


class IntakeContext(Preview):
    medications: str | None
    allergies: str | None
    matched: MatchedNames


class PreviousVisit(IntakeContext):
    date: str
    triage_specialty: str | None


class DoctorAI(BaseModel):
    source: Literal["llm", "fallback"]
    doctor_summary: str
    considerations: list[str]
    notice: str


class DoctorVisit(BaseModel):
    id: str
    status: Literal["pending", "accepted", "cancelled", "expired"]
    created_at: str
    specialty: Specialty
    urgency: str
    preview: Preview
    patient: IntakeContext | None
    previous_visits: list[PreviousVisit] | None
    ai: DoctorAI | None
