from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import scheduler
from app.core.database import get_db
from app.models import SyncRun
from app.schemas.sync import SyncRunRead, SyncStatusRead
from app.services import sync_service, youtube_client

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/status", response_model=SyncStatusRead)
def get_status(db: Session = Depends(get_db)) -> SyncStatusRead:
    last = db.query(SyncRun).order_by(SyncRun.started_at.desc()).first()
    sched_err = scheduler.last_error()
    next_at = scheduler.next_run_time()
    # Scheduler é considerado OK quando está rodando, sem erro pendente, e o
    # job tem next_run_time definido. Se qualquer um falhar, o frontend mostra
    # aviso no dashboard pra evitar mentir sobre "próximo sync".
    scheduler_ok = scheduler.is_running() and sched_err is None and next_at is not None
    return SyncStatusRead(
        interval_hours=scheduler.current_interval_hours(),
        next_run_at=next_at,
        last_run=last,
        scheduler_ok=scheduler_ok,
        scheduler_error=sched_err,
    )


@router.post("/run", response_model=SyncRunRead, status_code=status.HTTP_201_CREATED)
def run_now(db: Session = Depends(get_db)) -> SyncRunRead:
    try:
        return sync_service.run_sync(db, sync_type="manual")
    except youtube_client.APIKeyDecryptError as exc:
        # Diferencia "sem chave" de "configuracao quebrada" pra o usuario
        # saber que precisa rever APP_SECRET_KEY, nao re-cadastrar a chave.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except youtube_client.NoAPIKeyConfigured as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/runs", response_model=list[SyncRunRead])
def list_runs(limit: int = 50, db: Session = Depends(get_db)) -> list[SyncRunRead]:
    return (
        db.query(SyncRun)
        .order_by(SyncRun.started_at.desc())
        .limit(min(limit, 200))
        .all()
    )
