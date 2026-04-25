"""
Backfill de thumbnails para canais e vídeos já existentes no banco.

Diferente do `monitoring_service.snapshot_channel` (que custa 3 units/canal),
este script faz uma única chamada `channels.list` em LOTE de 50 IDs por vez,
gastando 1 unit por lote. Mesmo para tracked_videos: `videos.list` em lote.

Custo típico:
  - 200 canais sem thumb → 4 lotes × 1 unit = 4 units total
  - 50 vídeos sem thumb  → 1 lote × 1 unit = 1 unit total

Idempotente: só atualiza canais/vídeos com thumbnail_url=NULL.

Uso:
    python scripts/backfill_thumbnails.py                            # local default
    python scripts/backfill_thumbnails.py --base-url URL             # outro alvo
    python scripts/backfill_thumbnails.py --skip-channels            # só vídeos
    python scripts/backfill_thumbnails.py --skip-videos              # só canais
    python scripts/backfill_thumbnails.py --dry-run                  # mostra o plano
"""
from __future__ import annotations

import argparse
import io
import sys
from typing import Iterable, Optional

# Roda no contexto da app — precisa do venv da api/.
sys.path.insert(0, "api")

from app.core.database import SessionLocal  # noqa: E402
from app.models import Channel, TrackedVideo  # noqa: E402
from app.services import youtube_client  # noqa: E402
from app.services.monitoring_service import _pick_thumbnail  # noqa: E402

# UTF-8 console no Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _chunks(seq: list, size: int) -> Iterable[list]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def backfill_channels(db, client, dry_run: bool) -> int:
    rows = (
        db.query(Channel)
        .filter(Channel.thumbnail_url.is_(None))
        .all()
    )
    if not rows:
        print("[canais] nada a fazer — todos já têm thumb")
        return 0

    print(f"[canais] {len(rows)} sem thumb")
    by_yt: dict[str, Channel] = {c.youtube_channel_id: c for c in rows}
    ids = list(by_yt.keys())

    quota_lots = 0
    updated = 0
    not_found = 0

    for i, chunk in enumerate(_chunks(ids, 50), 1):
        quota_lots += 1
        if dry_run:
            print(f"  [DRY] lote {i}: {len(chunk)} canais → 1 unit")
            continue

        items = client.channels_by_ids(chunk)
        seen: set[str] = set()
        for item in items:
            yt_id = item.get("id")
            if not yt_id:
                continue
            seen.add(yt_id)
            ch = by_yt.get(yt_id)
            if ch is None:
                continue
            thumb = _pick_thumbnail(item.get("snippet") or {})
            if thumb:
                ch.thumbnail_url = thumb
                updated += 1

        # IDs do chunk que o YouTube não devolveu (canal deletado/banido)
        for yt_id in chunk:
            if yt_id not in seen:
                not_found += 1

        db.commit()
        print(f"  lote {i}: {len(chunk)} canais → {updated} atualizados (acum)")

    print(
        f"[canais] {updated} atualizados, {not_found} não encontrados no YouTube, "
        f"{quota_lots} units gastos"
    )
    return updated


def backfill_videos(db, client, dry_run: bool) -> int:
    rows = (
        db.query(TrackedVideo)
        .filter(TrackedVideo.thumbnail_url.is_(None))
        .all()
    )
    if not rows:
        print("[videos] nada a fazer — todos já têm thumb")
        return 0

    print(f"[videos] {len(rows)} sem thumb")
    by_yt: dict[str, TrackedVideo] = {v.youtube_video_id: v for v in rows}
    ids = list(by_yt.keys())

    quota_lots = 0
    updated = 0
    not_found = 0

    for i, chunk in enumerate(_chunks(ids, 50), 1):
        quota_lots += 1
        if dry_run:
            print(f"  [DRY] lote {i}: {len(chunk)} videos → 1 unit")
            continue

        items = client.videos_by_ids(chunk)
        seen: set[str] = set()
        for item in items:
            yt_id = item.get("id")
            if not yt_id:
                continue
            seen.add(yt_id)
            tv = by_yt.get(yt_id)
            if tv is None:
                continue
            thumb = _pick_thumbnail(item.get("snippet") or {})
            if thumb:
                tv.thumbnail_url = thumb
                updated += 1

        for yt_id in chunk:
            if yt_id not in seen:
                not_found += 1

        db.commit()
        print(f"  lote {i}: {len(chunk)} videos → {updated} atualizados (acum)")

    print(
        f"[videos] {updated} atualizados, {not_found} não encontrados no YouTube, "
        f"{quota_lots} units gastos"
    )
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill de thumbnails em lote")
    parser.add_argument(
        "--skip-channels",
        action="store_true",
        help="Não popular thumbs de canais",
    )
    parser.add_argument(
        "--skip-videos",
        action="store_true",
        help="Não popular thumbs de vídeos",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que faria, sem chamar YouTube nem gravar",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("** DRY-RUN — nenhuma chamada YouTube nem escrita no banco **\n")

    db = SessionLocal()
    try:
        client = None
        if not args.dry_run:
            client = youtube_client.build_from_db(db)

        if not args.skip_channels:
            backfill_channels(db, client, args.dry_run)
        else:
            print("[canais] SKIPPED")
        print()
        if not args.skip_videos:
            backfill_videos(db, client, args.dry_run)
        else:
            print("[videos] SKIPPED")
    finally:
        db.close()

    print("\nConcluído.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
