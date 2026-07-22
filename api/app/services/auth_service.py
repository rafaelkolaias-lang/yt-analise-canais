"""
Auth service — login, validação de sessão e troca de senha.

Modelo:
  - Sessões opacas na tabela `auth_sessions` (token em claro só existe na
    resposta do login; o banco guarda SHA-256). Revogáveis individualmente.
  - Expiração por cliente: web = 30 dias, desktop = 365 dias (o app do
    Windows guarda o token no PC pra não pedir login toda hora).
  - Bootstrap: `ensure_default_admin` cria `admin`/`admin` se a tabela de
    usuários estiver vazia (rodado pelo seed). O usuário DEVE trocar a senha
    na tela de Configurações.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core import security
from app.models import AuthSession, User

log = logging.getLogger(__name__)

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"

_TTL_BY_CLIENT = {
    "web": timedelta(days=30),
    "desktop": timedelta(days=365),
}


class InvalidCredentialsError(RuntimeError):
    """Usuário inexistente/inativo ou senha incorreta."""


class InvalidTokenError(RuntimeError):
    """Token ausente, desconhecido, expirado ou revogado."""


def ensure_default_admin(db: Session) -> bool:
    """
    Cria o usuário inicial `admin`/`admin` SE não existir nenhum usuário.
    Retorna True se criou. Idempotente — seguro rodar em todo seed.
    """
    if db.query(User).count() > 0:
        return False
    db.add(
        User(
            username=DEFAULT_ADMIN_USERNAME,
            password_hash=security.hash_password(DEFAULT_ADMIN_PASSWORD),
        )
    )
    db.commit()
    log.warning(
        "Usuário inicial '%s' criado com senha padrão — TROQUE a senha em "
        "Configurações no primeiro acesso.",
        DEFAULT_ADMIN_USERNAME,
    )
    return True


def login(
    db: Session, username: str, password: str, client: str = "web"
) -> tuple[str, AuthSession, User]:
    """
    Valida credenciais e cria sessão. Retorna (token_em_claro, sessao, user).
    Levanta InvalidCredentialsError em falha (mensagem única — não revela se
    o usuário existe).
    """
    user = (
        db.query(User)
        .filter(User.username == username.strip().lower(), User.is_active.is_(True))
        .one_or_none()
    )
    if user is None or not security.verify_password(password, user.password_hash):
        raise InvalidCredentialsError("Usuário ou senha inválidos.")

    client_norm = client if client in _TTL_BY_CLIENT else "web"
    token = security.generate_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=security.hash_token(token),
        client=client_norm,
        expires_at=datetime.utcnow() + _TTL_BY_CLIENT[client_norm],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return token, session, user


def validate_token(db: Session, token: str) -> User:
    """
    Resolve um token Bearer em User. Levanta InvalidTokenError se inválido.
    Atualiza `last_used_at` no máximo 1x/hora (evita write em toda request).
    """
    if not token:
        raise InvalidTokenError("Token ausente.")
    session = (
        db.query(AuthSession)
        .filter(AuthSession.token_hash == security.hash_token(token))
        .one_or_none()
    )
    now = datetime.utcnow()
    if (
        session is None
        or session.revoked_at is not None
        or session.expires_at < now
    ):
        raise InvalidTokenError("Sessão inválida ou expirada.")

    user = (
        db.query(User)
        .filter(User.id == session.user_id, User.is_active.is_(True))
        .one_or_none()
    )
    if user is None:
        raise InvalidTokenError("Usuário inativo.")

    if session.last_used_at is None or (now - session.last_used_at) > timedelta(hours=1):
        try:
            session.last_used_at = now
            db.commit()
        except Exception:  # noqa: BLE001 — cosmético, nunca bloqueia a request
            db.rollback()
    return user


def logout(db: Session, token: str) -> bool:
    """Revoga a sessão do token atual. Retorna True se revogou algo."""
    session = (
        db.query(AuthSession)
        .filter(
            AuthSession.token_hash == security.hash_token(token),
            AuthSession.revoked_at.is_(None),
        )
        .one_or_none()
    )
    if session is None:
        return False
    session.revoked_at = datetime.utcnow()
    db.commit()
    return True


def change_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
    keep_token: Optional[str] = None,
) -> None:
    """
    Troca a senha do usuário e revoga TODAS as outras sessões (menos a do
    `keep_token`, pra não deslogar quem acabou de trocar).
    """
    if not security.verify_password(current_password, user.password_hash):
        raise InvalidCredentialsError("Senha atual incorreta.")
    if len(new_password) < 4:
        raise ValueError("Nova senha deve ter pelo menos 4 caracteres.")

    user.password_hash = security.hash_password(new_password)

    keep_hash = security.hash_token(keep_token) if keep_token else None
    sessions = (
        db.query(AuthSession)
        .filter(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
        )
        .all()
    )
    now = datetime.utcnow()
    for s in sessions:
        if keep_hash is not None and s.token_hash == keep_hash:
            continue
        s.revoked_at = now
    db.commit()
