from typing import Annotated

from fastapi import APIRouter, Query

from app.agent.dictionaries import Kind, search
from app.schemas.common import ErrorResponse
from app.schemas.dictionaries import DictionaryResponse

router = APIRouter(prefix="/v1/dictionaries", tags=["dictionaries"])


@router.get("/{kind}", response_model=DictionaryResponse, responses={422: {"model": ErrorResponse}})
async def dictionary(
    kind: Kind,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DictionaryResponse:
    return DictionaryResponse(kind=kind, entries=search(kind, q or "", limit))
