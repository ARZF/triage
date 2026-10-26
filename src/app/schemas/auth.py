from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from app.schemas.triage import Specialty, SpecialtyCode
from app.schemas.admin import ReviewStatus

Username = Annotated[str, BeforeValidator(lambda value: value.lower() if isinstance(value, str) else value), StringConstraints(pattern=r"^[a-z0-9_.-]{3,32}$")]
Password = Annotated[str, Field(min_length=8, max_length=128, repr=False)]
Expertise = Annotated[list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=40)]], Field(min_length=2, max_length=3)]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Username
    password: Password


class PatientRegistration(LoginRequest):
    role: Literal["patient"]


class DoctorRegistration(LoginRequest):
    role: Literal["doctor"]
    license_number: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9-]{4,20}$")]
    name_fa: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
    specialty_code: SpecialtyCode
    expertise: Expertise


Registration = Annotated[PatientRegistration | DoctorRegistration, Field(discriminator="role")]


class DoctorAccount(BaseModel):
    verified: bool
    status: ReviewStatus
    review_note: str | None
    available: bool
    specialty: Specialty


class User(BaseModel):
    id: str
    role: Literal["patient", "doctor", "admin"]
    username: str
    display_name: str
    doctor: DoctorAccount | None


class AuthResponse(BaseModel):
    user: User
