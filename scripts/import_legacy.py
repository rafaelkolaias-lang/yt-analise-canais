"""
Importação one-shot do projeto desktop antigo para o stack web.

Origem: E:\\Automacao-YT\\yt-analise-canais\\dados\\
  - config.json         → API keys do YouTube (PUT /api/settings/youtube.api_keys)
  - monitorados.json    → canais ativos (POST /api/monitoring/channels)
  - canais_listados.csv → canais "vistos" (POST + PATCH para paused)

Uso:
    python scripts/import_legacy.py                            # contra local (default)
    python scripts/import_legacy.py --base-url URL             # contra outro alvo
    python scripts/import_legacy.py --skip-keys                # não tocar em api_keys
    python scripts/import_legacy.py --skip-listados            # não importar os 232
    python scripts/import_legacy.py --dry-run                  # só mostra o que faria

Requisitos:
  - API rodando no --base-url (default http://localhost:8000).
  - Banco com schema (alembic upgrade head já feito).

Idempotente:
  - PUT em api_keys sempre sobrescreve (intencional).
  - POST de canais já cadastrados retorna o existente sem erro.
  - PATCH para paused é seguro de repetir.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from pathlib import Path
from typing import Optional

import urllib.error
import urllib.request

# Console do Windows é cp1252 por padrão e quebra ao printar Unicode (acentos,
# setas, etc). Reabrimos stdout/stderr em UTF-8 para o script ser portável.
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DEFAULT_LEGACY_DIR = Path(r"E:\Automacao-YT\yt-analise-canais\dados")
DEFAULT_BASE_URL = "http://localhost:8000"


# =============================================================================
# Helpers HTTP (urllib, sem deps externas — script roda em qualquer Python 3.11)
# =============================================================================
def _request(
    method: str, url: str, body: Optional[dict] = None, timeout: int = 30
) -> tuple[int, dict | str]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(payload)
            except json.JSONDecodeError:
                return resp.status, payload
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(payload)
        except json.JSONDecodeError:
            return e.code, payload
    except urllib.error.URLError as e:
        return 0, f"URL error: {e}"


def get(url: str) -> tuple[int, dict | str]:
    return _request("GET", url)


def put(url: str, body: dict) -> tuple[int, dict | str]:
    return _request("PUT", url, body)


def post(url: str, body: dict) -> tuple[int, dict | str]:
    return _request("POST", url, body)


def patch(url: str, body: dict) -> tuple[int, dict | str]:
    return _request("PATCH", url, body)


# =============================================================================
# Etapas
# =============================================================================
def health_check(base_url: str) -> bool:
    print(f"→ pingando {base_url}/health …", end=" ")
    code, body = get(f"{base_url}/health")
    if code == 200 and isinstance(body, dict) and body.get("status") == "ok":
        print(f"OK ({body.get('app')}, env={body.get('env')})")
        return True
    print(f"FALHOU (HTTP {code}, body={body!r})")
    return False


def import_api_keys(base_url: str, config_path: Path, dry_run: bool) -> bool:
    print(f"\n[1/3] API keys do YouTube ← {config_path}")
    if not config_path.exists():
        print(f"  ✗arquivo não encontrado: {config_path}")
        return False

    with config_path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    keys = cfg.get("API_KEYS") or []
    keys = [k.strip() for k in keys if isinstance(k, str) and k.strip()]
    if not keys:
        print("  - nenhuma key encontrada em API_KEYS")
        return True

    print(f"  - {len(keys)} key(s) encontradas no config.json")
    value = "\n".join(keys)

    if dry_run:
        print(f"  [DRY-RUN] PUT /api/settings/youtube.api_keys com {len(keys)} keys")
        return True

    code, body = put(f"{base_url}/api/settings/youtube.api_keys", {"value": value})
    if code != 200:
        print(f"  ✗PUT falhou (HTTP {code}): {body!r}")
        return False

    print("  ✓keys gravadas (cifradas com Fernet pelo backend)")
    return True


def load_monitorados(path: Path) -> list[dict]:
    if not path.exists():
        print(f"  ✗arquivo não encontrado: {path}")
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    chans = data.get("channels", [])
    return [c for c in chans if c.get("status") == "active" and c.get("channel_id")]


def load_listados(path: Path) -> list[dict]:
    if not path.exists():
        print(f"  ✗arquivo não encontrado: {path}")
        return []
    out = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = (row.get("channel_id") or "").strip()
            if cid.startswith("UC"):
                out.append({"channel_id": cid, "title": row.get("channel_title", "")})
    return out


def post_channel(
    base_url: str, channel_id: str, label: str, dry_run: bool
) -> Optional[int]:
    """Cria ou retorna canal existente. Devolve id interno (ou None em erro)."""
    if dry_run:
        print(f"  [DRY-RUN] POST channel {channel_id} ({label})")
        return -1

    code, body = post(
        f"{base_url}/api/monitoring/channels", {"youtube_channel_id": channel_id}
    )
    if code in (200, 201) and isinstance(body, dict):
        return int(body.get("id"))
    print(f"    ✗{channel_id}: HTTP {code} — {body!r}")
    return None


def pause_channel(base_url: str, channel_db_id: int, dry_run: bool) -> bool:
    if dry_run:
        return True
    code, body = patch(
        f"{base_url}/api/monitoring/channels/{channel_db_id}", {"status": "paused"}
    )
    if code != 200:
        print(f"    ✗PATCH paused falhou (HTTP {code}): {body!r}")
        return False
    return True


def import_monitorados(base_url: str, path: Path, dry_run: bool) -> set[str]:
    print(f"\n[2/3] Canais monitorados (active) ← {path}")
    chans = load_monitorados(path)
    print(f"  - {len(chans)} canais ativos no monitorados.json")

    seen: set[str] = set()
    ok = 0
    fail = 0
    for c in chans:
        cid = c["channel_id"]
        title = c.get("title") or "(sem título)"
        seen.add(cid)
        new_id = post_channel(base_url, cid, title, dry_run)
        if new_id is None:
            fail += 1
            continue
        ok += 1
        print(f"  ✓{cid}  {title}")
        time.sleep(0.05)  # gentil com a YouTube API rate limit no resolve do nome

    print(f"  -- {ok} ok, {fail} falhas")
    return seen


def import_listados(
    base_url: str, path: Path, already_imported: set[str], dry_run: bool
) -> None:
    print(f"\n[3/3] Canais listados (paused) ← {path}")
    rows = load_listados(path)
    pending = [r for r in rows if r["channel_id"] not in already_imported]
    skipped_dup = len(rows) - len(pending)
    print(
        f"  - {len(rows)} no CSV; {skipped_dup} já estão na lista de monitorados; "
        f"{len(pending)} a importar como paused"
    )

    ok = 0
    fail = 0
    for i, r in enumerate(pending, 1):
        cid = r["channel_id"]
        title = r.get("title") or "(sem título)"

        new_id = post_channel(base_url, cid, title, dry_run)
        if new_id is None:
            fail += 1
            continue
        if not dry_run and not pause_channel(base_url, new_id, dry_run):
            fail += 1
            continue
        ok += 1
        if i % 10 == 0 or i == len(pending):
            print(f"  ... {i}/{len(pending)} processados")
        time.sleep(0.05)

    print(f"  -- {ok} ok (status=paused), {fail} falhas")


# =============================================================================
# CLI
# =============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importa canais e API keys do projeto desktop antigo."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="URL da API")
    parser.add_argument(
        "--legacy-dir",
        type=Path,
        default=DEFAULT_LEGACY_DIR,
        help="Pasta dados/ do projeto antigo",
    )
    parser.add_argument(
        "--skip-keys", action="store_true", help="Pular import das API keys"
    )
    parser.add_argument(
        "--skip-listados",
        action="store_true",
        help="Pular import dos 232 canais como paused",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Não escreve nada — só mostra o plano"
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    legacy_dir = args.legacy_dir

    print(f"Alvo: {base_url}")
    print(f"Origem: {legacy_dir}")
    if args.dry_run:
        print("** DRY-RUN — nenhuma escrita será feita **")
    print()

    if not health_check(base_url):
        print("\nAbortando — API não está respondendo.")
        return 1

    if not args.skip_keys:
        if not import_api_keys(base_url, legacy_dir / "config.json", args.dry_run):
            print("\nFalha ao gravar API keys — abortando antes dos canais")
            print("(import de canais precisa de keys pra resolver os nomes)")
            return 1
    else:
        print("\n[1/3] API keys: SKIPPED (--skip-keys)")

    seen = import_monitorados(base_url, legacy_dir / "monitorados.json", args.dry_run)

    if not args.skip_listados:
        import_listados(
            base_url, legacy_dir / "canais_listados.csv", seen, args.dry_run
        )
    else:
        print("\n[3/3] Canais listados: SKIPPED (--skip-listados)")

    print("\nConcluído.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
