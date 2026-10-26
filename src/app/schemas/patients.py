from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictInt, StringConstraints, field_validator, model_validator

from app.agent.intake import Collected, parse_measurement
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


ProfileText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Measurement = Annotated[float, BeforeValidator(parse_measurement)]


class PatientProfile(BaseModel):
    age: Annotated[StrictInt, Field(ge=0, le=120)] | None = None
    height_cm: Measurement | None = None
    weight_kg: Measurement | None = None
    medical_history: ProfileText | None = None
    medications: ProfileText | None = None
    medication_history: ProfileText | None = None
    food_allergies: ProfileText | None = None
    allergies: ProfileText | None = None


class PatientProfilePatch(PatientProfile):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def non_null(cls, value):
        if value is None:
            raise ValueError("Profile fields cannot be null")
        return value

    @model_validator(mode="after")
    def non_empty(self):
        if not self.model_fields_set:
            raise ValueError("At least one profile field is required")
        return self


class PatientProfileResponse(BaseModel):
    profile: PatientProfile
    updated_at: str | None
    complete: bool
