from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import admin_user
from app.schemas.admin import AuditPage, DoctorPage, DoctorReview, ReviewNote, ReviewStatus
from app.schemas.common import ErrorResponse
from app.services import admin

router = APIRouter(prefix="/v1/admin", tags=["admin"], responses={
    status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 422)
})


@router.get("/doctors", response_model=DoctorPage)
def doctors(status: ReviewStatus = "pending", limit: Annotated[int, Query(ge=1, le=100)] = 50,
            offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
            user: dict = Depends(admin_user)) -> dict:
    return admin.list_doctors(status, limit, offset)


@router.post("/doctors/{doctor_id}/approve", response_model=DoctorReview)
def approve(doctor_id: str, user: dict = Depends(admin_user)) -> dict:
    return admin.review(doctor_id, user["id"], "approve")


@router.post("/doctors/{doctor_id}/reject", response_model=DoctorReview)
def reject(doctor_id: str, body: ReviewNote, user: dict = Depends(admin_user)) -> dict:
    return admin.review(doctor_id, user["id"], "reject", body.note)


@router.post("/doctors/{doctor_id}/suspend", response_model=DoctorReview)
def suspend(doctor_id: str, body: ReviewNote, user: dict = Depends(admin_user)) -> dict:
    return admin.review(doctor_id, user["id"], "suspend", body.note)


@router.get("/audit", response_model=AuditPage)
def audit(limit: Annotated[int, Query(ge=1, le=100)] = 50, user: dict = Depends(admin_user)) -> dict:
    return admin.audit(limit)
