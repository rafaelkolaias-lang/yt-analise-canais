from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.settings import AppSettingRead, AppSettingUpdate
from app.services import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=list[AppSettingRead])
def list_all(db: Session = Depends(get_db)) -> list[AppSettingRead]:
    return settings_service.list_settings(db)


@router.get("/{key}", response_model=AppSettingRead)
def get_one(key: str, db: Session = Depends(get_db)) -> AppSettingRead:
    result = settings_service.get_setting(db, key)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"setting '{key}' not found")
    return result


@router.put("/{key}", response_model=AppSettingRead)
def update_one(
    key: str,
    payload: AppSettingUpdate,
    db: Session = Depends(get_db),
) -> AppSettingRead:
    try:
        result = settings_service.update_setting(db, key, payload.value)
    except ValueError as exc:
        # Valor incoerente com o tipo da setting → 400 com mensagem clara.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"setting '{key}' not found")
    return result
