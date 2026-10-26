from fastapi import APIRouter, Depends, Request, Response

from app.agent.doctors import load_doctors
from app.api.deps import current_user
from app.core.config import Settings
from app.schemas.auth import AuthResponse, LoginRequest, PasswordChange, Registration
from app.schemas.common import ErrorResponse
from app.services import accounts

router = APIRouter(prefix="/v1", tags=["accounts"])


def set_cookie(response: Response, token: str) -> None:
    settings = Settings()
    response.set_cookie(
        "session", token, httponly=True, samesite="lax", path="/",
        max_age=settings.session_ttl_hours * 3600, secure=settings.cookie_secure,
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie("session", path="/", httponly=True, samesite="lax", secure=Settings().cookie_secure)


@router.post("/auth/register", status_code=201, response_model=AuthResponse, responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
def register(body: Registration, response: Response) -> dict:
    user, token = accounts.register(body)
    set_cookie(response, token)
    return {"user": accounts.public_user(user)}


@router.post("/auth/login", response_model=AuthResponse, responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
def login(body: LoginRequest, response: Response) -> dict:
    user, token = accounts.login(body.username, body.password)
    set_cookie(response, token)
    return {"user": accounts.public_user(user)}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, user: dict = Depends(current_user)) -> Response:
    accounts.logout(request.cookies.get("session"))
    response = Response(status_code=204)
    clear_cookie(response)
    return response


@router.get("/auth/me", response_model=AuthResponse, responses={401: {"model": ErrorResponse}})
def me(user: dict = Depends(current_user)) -> dict:
    return {"user": accounts.public_user(user)}


@router.get("/specialties")
def specialties() -> list[dict]:
    return [{"code": entry["code"], "name_fa": entry["name_fa"]} for entry in load_doctors()["specialties"]]


@router.post("/me/password", status_code=204, responses={status: {"model": ErrorResponse} for status in (401, 409, 422, 429)})
def password(body: PasswordChange, request: Request, user: dict = Depends(current_user)) -> Response:
    accounts.change_password(user, request.cookies["session"], body.current_password, body.new_password)
    return Response(status_code=204)
