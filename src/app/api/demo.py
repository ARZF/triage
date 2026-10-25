from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/demo", response_class=FileResponse, include_in_schema=False)
async def demo() -> FileResponse:
    return FileResponse(
        Path(__file__).resolve().parents[1] / "static" / "index.html",
        media_type="text/html",
    )
