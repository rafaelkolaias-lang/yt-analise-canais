from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    # "web" | "desktop" — desktop ganha sessão de longa duração.
    client: str = Field(default="web", max_length=32)


class LoginResponse(BaseModel):
    token: str
    expires_at: datetime
    user: UserRead


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=4, max_length=128)


class AuthOpResponse(BaseModel):
    ok: bool
