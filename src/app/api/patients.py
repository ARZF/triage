from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.agent.sessions import delete_patient, patient_history
from app.api.auth import clear_cookie
from app.api.deps import patient_user
from app.schemas.common import ErrorResponse
from app.schemas.patients import HistoryVisit, PatientProfilePatch, PatientProfileResponse
from app.services import accounts

router = APIRouter(prefix="/v1", tags=["patient"], responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}})


@router.get("/me/history", response_model=list[HistoryVisit], responses={422: {"model": ErrorResponse}})
def history(limit: Annotated[int, Query(ge=1, le=50)] = 10, user: dict = Depends(patient_user)) -> list[dict]:
    return patient_history(user["patient_id"], limit)


@router.delete("/me", status_code=204)
def forget(user: dict = Depends(patient_user)) -> Response:
    delete_patient(user["patient_id"])
    response = Response(status_code=204)
    clear_cookie(response)
    return response


@router.get("/patient/profile", response_model=PatientProfileResponse)
def profile(user: dict = Depends(patient_user)) -> dict:
    return accounts.patient_profile(user["patient_id"])


@router.patch("/patient/profile", response_model=PatientProfileResponse, responses={422: {"model": ErrorResponse}})
def update_profile(body: PatientProfilePatch, user: dict = Depends(patient_user)) -> dict:
    return accounts.update_patient_profile(user["patient_id"], body.model_dump(exclude_unset=True))
