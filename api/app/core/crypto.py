"""
Criptografia simétrica para secrets persistidos no banco (ex.: YouTube API keys).

Usa Fernet (AES-128-CBC + HMAC-SHA256) com chave mestra derivada de APP_SECRET_KEY.
A chave mestra NUNCA é persistida no banco — fica apenas em variável de ambiente.
Se APP_SECRET_KEY for perdida, os valores cifrados tornam-se irrecuperáveis.
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class CryptoNotConfiguredError(RuntimeError):
    pass


class CryptoDecryptError(RuntimeError):
    pass


@lru_cache
def _fernet() -> Fernet:
    secret = get_settings().app_secret_key
    if not secret:
        raise CryptoNotConfiguredError(
            "APP_SECRET_KEY não configurado. Defina no .env antes de cifrar/decifrar secrets."
        )
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise CryptoDecryptError("Token inválido ou APP_SECRET_KEY diferente da usada ao cifrar.") from exc


def mask(plaintext: str, visible: int = 4) -> str:
    if not plaintext:
        return ""
    if len(plaintext) <= visible:
        return "*" * len(plaintext)
    return "*" * (len(plaintext) - visible) + plaintext[-visible:]
