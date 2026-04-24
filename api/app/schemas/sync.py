from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    channels_processed: int
    videos_processed: int
    notes: Optional[str] = None


class SyncStatusRead(BaseModel):
    interval_hours: int
    next_run_at: Optional[datetime] = None
    last_run: Optional[SyncRunRead] = None
