"""
Router /api/auth — login, logout, sessão atual e troca de senha.

`/login` é a ÚNICA rota aberta deste router; as demais exigem Bearer token
(dependency aplicada rota a rota aqui, já que o router em si precisa ficar
fora da proteção global pra permitir o login).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import current_token, require_auth
from app.core.database import get_db
from app.models import User
from app.schemas.auth import (
    AuthOpResponse,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    UserRead,
)
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    try:
        token, session, user = auth_service.login(
            db, req.username, req.password, client=req.client
        )
    except auth_service.InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return LoginResponse(
        token=token,
        expires_at=session.expires_at,
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(require_auth)) -> UserRead:
    return UserRead.model_validate(user)


@router.post("/logout", response_model=AuthOpResponse)
def logout(
    user: User = Depends(require_auth),
    token: str = Depends(current_token),
    db: Session = Depends(get_db),
) -> AuthOpResponse:
    return AuthOpResponse(ok=auth_service.logout(db, token))


@router.post("/change-password", response_model=AuthOpResponse)
def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(require_auth),
    token: str = Depends(current_token),
    db: Session = Depends(get_db),
) -> AuthOpResponse:
    try:
        auth_service.change_password(
            db,
            user,
            current_password=req.current_password,
            new_password=req.new_password,
            keep_token=token,
        )
    except auth_service.InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return AuthOpResponse(ok=True)
