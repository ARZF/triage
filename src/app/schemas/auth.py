from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.schemas.triage import Specialty, SpecialtyCode
from app.schemas.admin import ReviewStatus

Username = Annotated[str, BeforeValidator(lambda value: value.lower() if isinstance(value, str) else value), StringConstraints(pattern=r"^[a-z0-9_.-]{3,32}$")]
Password = Annotated[str, Field(min_length=8, max_length=128, repr=False)]
Expertise = Annotated[list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=40)]], Field(min_length=2, max_length=3)]
DoctorName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
LicenseNumber = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9-]{4,20}$")]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Username
    password: Password


class PatientRegistration(LoginRequest):
    role: Literal["patient"]


class DoctorRegistration(LoginRequest):
    role: Literal["doctor"]
    license_number: LicenseNumber
    name_fa: DoctorName
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


class DoctorProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name_fa: DoctorName | None = None
    specialty_code: SpecialtyCode | None = None
    expertise: Expertise | None = None
    license_number: LicenseNumber | None = None

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


class DoctorProfile(BaseModel):
    name_fa: str
    specialty: Specialty
    expertise: list[str]
    license_number: str | None
    score: float | None
    status: ReviewStatus
    review_note: str | None
    resubmitted_at: str | None


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128, repr=False)
    new_password: Password

    @model_validator(mode="after")
    def different(self):
        if self.current_password == self.new_password:
            raise ValueError("New password must be different")
        return self
