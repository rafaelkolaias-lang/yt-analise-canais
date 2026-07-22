"""
Dependency de autenticação global.

`require_auth` é aplicada em `main.py` via `dependencies=[Depends(require_auth)]`
nos routers protegidos. Rotas abertas (login, health, version, root) ficam fora.

O token viaja em `Authorization: Bearer <token>` — tanto o site quanto o app
do Windows usam o mesmo esquema.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User
from app.services import auth_service

# auto_error=False: queremos devolver 401 com mensagem própria (e não 403
# padrão do FastAPI quando o header está ausente).
_bearer = HTTPBearer(auto_error=False)


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autenticado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return auth_service.validate_token(db, credentials.credentials)
    except auth_service.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )


def current_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Token em claro da request atual (para logout / keep na troca de senha)."""
    return credentials.credentials if credentials else ""
