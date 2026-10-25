from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.agent.sessions import delete_patient, patient_history
from app.api.auth import clear_cookie
from app.api.deps import patient_user
from app.schemas.common import ErrorResponse
from app.schemas.patients import HistoryVisit

router = APIRouter(prefix="/v1/me", tags=["patient"], responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}})


@router.get("/history", response_model=list[HistoryVisit], responses={422: {"model": ErrorResponse}})
def history(limit: Annotated[int, Query(ge=1, le=50)] = 10, user: dict = Depends(patient_user)) -> list[dict]:
    return patient_history(user["patient_id"], limit)


@router.delete("", status_code=204)
def forget(user: dict = Depends(patient_user)) -> Response:
    delete_patient(user["patient_id"])
    response = Response(status_code=204)
    clear_cookie(response)
    return response
