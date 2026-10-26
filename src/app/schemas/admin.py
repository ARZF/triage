from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.schemas.triage import Specialty

ReviewStatus = Literal["pending", "approved", "rejected", "suspended"]


class ReviewNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]


class DoctorReview(BaseModel):
    id: str
    name_fa: str
    specialty: Specialty
    expertise: list[str]
    license_number: str | None
    registered_at: str
    status: ReviewStatus
    reviewed_at: str | None
    review_note: str | None


class DoctorPage(BaseModel):
    items: list[DoctorReview]
    total: int


class AuditItem(BaseModel):
    id: int
    action: Literal["approve", "reject", "suspend"]
    doctor_id: str
    doctor_name_fa: str | None
    from_status: ReviewStatus | None
    to_status: ReviewStatus | None
    note: str | None
    created_at: str


class AuditPage(BaseModel):
    items: list[AuditItem]
