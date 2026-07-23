"""Registration, login, logout, and session endpoints."""

from fastapi import APIRouter, Request, Response, status
from app.api.dependencies import CurrentUserDep, SessionDep
from app.core.security import create_access_token
from app.schemas.auth import LoginRequest, SignUpRequest
from app.schemas.common import ErrorResponse
from app.schemas.user import UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/signup", response_model=UserRead, status_code=status.HTTP_201_CREATED, responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
async def signup(payload: SignUpRequest, session: SessionDep) -> UserRead:
    user = await AuthService(session).register(payload)
    return UserRead.model_validate(user)


@router.post("/login", response_model=UserRead, responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
async def login(payload: LoginRequest, request: Request, response: Response, session: SessionDep) -> UserRead:
    user = await AuthService(session).authenticate(payload)
    settings = request.app.state.settings
    token = create_access_token(
        subject=user.id,
        secret=settings.jwt_secret_key.get_secret_value(),
        lifetime_seconds=settings.jwt_access_token_minutes * 60,
    )
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.jwt_access_token_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return UserRead.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    response.delete_cookie(request.app.state.settings.auth_cookie_name, path="/")


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUserDep) -> UserRead:
    return UserRead.model_validate(user)
