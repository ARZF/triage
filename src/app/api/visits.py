from typing import Literal

from fastapi import APIRouter, Depends, Response

from app.api.deps import doctor_user, no_body, patient_user, verified_doctor
from app.schemas.auth import DoctorProfile, DoctorProfilePatch
from app.schemas.common import ErrorResponse
from app.schemas.visits import Availability, DoctorVisit, PatientVisit, VisitRequest
from app.services import doctors, visits

router = APIRouter(prefix="/v1", tags=["visit requests"], responses={
    status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 422)
})


@router.post("/visit-requests", status_code=201, response_model=PatientVisit)
def create_request(body: VisitRequest, user: dict = Depends(patient_user)) -> dict:
    return visits.create(user["patient_id"], body.session_id)


@router.get("/visit-requests", response_model=list[PatientVisit])
def own_requests(user: dict = Depends(patient_user)) -> list[dict]:
    return visits.patient_requests(user["patient_id"])


@router.post("/visit-requests/{request_id}/cancel", response_model=PatientVisit)
def cancel_request(request_id: str, user: dict = Depends(patient_user)) -> dict:
    return visits.cancel(user["patient_id"], request_id)


@router.put("/doctor/availability", response_model=Availability)
def availability(body: Availability, user: dict = Depends(verified_doctor)) -> dict:
    return doctors.set_available(user["doctor_id"], body.available)


@router.get("/doctor/requests", response_model=list[DoctorVisit])
def doctor_requests(status: Literal["pending", "accepted"] | None = None, user: dict = Depends(verified_doctor)) -> list[dict]:
    return visits.doctor_requests(user["doctor_id"], status)


@router.post("/doctor/requests/{request_id}/accept", response_model=DoctorVisit)
def accept_request(request_id: str, user: dict = Depends(verified_doctor)) -> dict:
    return visits.accept(user["doctor_id"], request_id)


@router.post("/doctor/heartbeat", status_code=204, dependencies=[Depends(no_body)])
def heartbeat(user: dict = Depends(verified_doctor)) -> Response:
    visits.heartbeat(user["doctor_id"])
    return Response(status_code=204)


@router.get("/doctor/profile", response_model=DoctorProfile)
def doctor_profile(user: dict = Depends(doctor_user)) -> dict:
    return doctors.profile(user["doctor_id"])


@router.patch("/doctor/profile", response_model=DoctorProfile)
def update_doctor_profile(body: DoctorProfilePatch, user: dict = Depends(doctor_user)) -> dict:
    return doctors.update_profile(user["doctor_id"], body.model_dump(exclude_unset=True))
