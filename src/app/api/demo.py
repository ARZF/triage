from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()
STATIC = Path(__file__).resolve().parents[1] / "static"


@router.get("/demo", response_class=FileResponse, include_in_schema=False)
async def demo() -> FileResponse:
    return FileResponse(STATIC / "index.html", media_type="text/html")


@router.get("/login", response_class=FileResponse, include_in_schema=False)
async def login() -> FileResponse:
    return FileResponse(STATIC / "login.html", media_type="text/html")


@router.get("/doctor", response_class=FileResponse, include_in_schema=False)
async def doctor() -> FileResponse:
    return FileResponse(STATIC / "doctor.html", media_type="text/html")


@router.get("/admin", response_class=FileResponse, include_in_schema=False)
async def admin() -> FileResponse:
    return FileResponse(STATIC / "admin.html", media_type="text/html")


@router.get("/assets/shell.css", response_class=FileResponse, include_in_schema=False)
async def shell_css() -> FileResponse:
    return FileResponse(STATIC / "shell.css", media_type="text/css", headers={"Cache-Control": "no-cache"})


@router.get("/assets/shell.js", response_class=FileResponse, include_in_schema=False)
async def shell_js() -> FileResponse:
    return FileResponse(STATIC / "shell.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})
