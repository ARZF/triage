from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response

from app.agent.sessions import delete_patient, patient_history
from app.schemas.common import ErrorResponse
from app.schemas.patients import HistoryVisit

router = APIRouter(prefix="/v1/patients", tags=["patients"])


@router.get(
    "/{patient_id}/history", response_model=list[HistoryVisit],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def history(patient_id: str, limit: Annotated[int, Query(ge=1, le=50)] = 10) -> list[dict]:
    try:
        return patient_history(patient_id, limit)
    except KeyError:
        raise HTTPException(status_code=404) from None


@router.delete("/{patient_id}", status_code=204, responses={404: {"model": ErrorResponse}})
def forget(patient_id: str) -> Response:
    try:
        delete_patient(patient_id)
    except KeyError:
        raise HTTPException(status_code=404) from None
    return Response(status_code=204)
