"""
Cliente YouTube Data API v3 — httpx sync, com rotação de keys.

Responsabilidades:
  - Ler `youtube.api_keys` (CSV cifrado) do banco e decifrar.
  - Rotacionar keys quando uma estoura quota (HTTP 403 + 'quota'/'forbidden').
  - Contar custo por request (tabela `QUOTA_COST`) contra `youtube.api_key_daily_quota`.
  - **Persistir** o consumo agregado em `app_settings.youtube.quota_usage_today`
    para que a UI da central de notificações mostre dado real (sobrevive a
    restart/deploy e converge entre processos com janela de leitura).
  - Expor search/videos/channels como funções simples que já fazem a retentativa.

Convenções:
  - Rollover diário em UTC (casa com o reset oficial da quota do YouTube).
  - Se nenhuma key tem saldo, levanta `QuotaExceeded`.
  - Se key é inválida (HTTP 400 keyInvalid), levanta `InvalidAPIKey`.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.core.crypto import decrypt
from app.models import AppSetting

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# Custos oficiais por endpoint (YouTube Data API v3, units/request)
QUOTA_COST = {
    "search": 100,
    "videos": 1,
    "channels": 1,
    "playlistItems": 1,
}

# Chave de app_settings onde gravamos o estado agregado de uso diário.
QUOTA_USAGE_SETTING_KEY = "youtube.quota_usage_today"


class QuotaExceeded(RuntimeError):
    pass


class InvalidAPIKey(RuntimeError):
    pass


class NoAPIKeyConfigured(RuntimeError):
    pass


def _today_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class YouTubeClient:
    """
    Cliente com rotação automática de keys.

    Não é thread-safe — criar uma instância por request HTTP (via factory
    `build_from_db`), não reutilizar entre requests.

    O contador `used` é hidratado a partir de `app_settings.youtube.quota_usage_today`
    no `build_from_db`, então diferentes processos convergem entre si na próxima
    instância. Toda request bem-sucedida grava o novo estado de volta.
    """
    keys: list[str]
    daily_quota: int
    used: list[int] = field(default_factory=list)
    current: int = 0
    # Sessão DB usada para persistir uso agregado. Opcional: se None, o client
    # funciona normalmente mas sem persistir (modo legado).
    db: Optional[Session] = None
    # Data UTC corrente do estado em memória. Usada pra detectar rollover entre
    # requests dentro do mesmo processo (raro, mas possível com workers longos).
    date_utc: str = field(default_factory=_today_utc_str)
    # Último evento de consumo: {"at": ISO, "label": str, "cost": int, "key_index": int}
    last_event: Optional[dict] = None

    def __post_init__(self) -> None:
        if not self.keys:
            raise NoAPIKeyConfigured(
                "Nenhuma API key cadastrada. Configure em /configuracoes (youtube.api_keys)."
            )
        if len(self.used) != len(self.keys):
            # Caso a quantidade de keys mude entre uma persistência e outra,
            # normaliza pro tamanho atual sem perder o que dá.
            self.used = (self.used + [0] * len(self.keys))[: len(self.keys)]

    def _pick_key(self, cost: int) -> int:
        n = len(self.keys)
        for offset in range(n):
            idx = (self.current + offset) % n
            if self.daily_quota - self.used[idx] >= cost:
                self.current = idx
                return idx
        raise QuotaExceeded(
            f"Todas as {n} API key(s) atingiram o limite diário ({self.daily_quota})."
        )

    def _maybe_rollover(self) -> None:
        """Se virou o dia em UTC desde o último estado em memória, zera contadores."""
        today = _today_utc_str()
        if today != self.date_utc:
            self.date_utc = today
            self.used = [0] * len(self.keys)
            self.last_event = None

    def _persist_state(self) -> None:
        """
        Grava o estado atual em `app_settings.youtube.quota_usage_today` como JSON.
        Silencioso em falha — o consumo real do YouTube não pode ser bloqueado por
        problema de telemetria.
        """
        if self.db is None:
            return
        payload = {
            "date_utc": self.date_utc,
            "used_per_key": list(self.used),
            "last_event": self.last_event,
        }
        try:
            row = (
                self.db.query(AppSetting)
                .filter_by(key=QUOTA_USAGE_SETTING_KEY)
                .one_or_none()
            )
            value = json.dumps(payload, separators=(",", ":"))
            if row is None:
                self.db.add(
                    AppSetting(
                        key=QUOTA_USAGE_SETTING_KEY,
                        value=value,
                        value_type="json",
                        is_secret=False,
                        description=(
                            "Estado persistido de consumo da cota diária do "
                            "YouTube por API key (rollover diário UTC)."
                        ),
                    )
                )
            else:
                row.value = value
            self.db.commit()
        except Exception as exc:  # pragma: no cover
            # Não derruba a request por causa de telemetria.
            print(f"[youtube_client] falha ao persistir quota_usage_today: {exc}")
            try:
                self.db.rollback()
            except Exception:
                pass

    def _get(self, endpoint: str, params: dict, event_label: Optional[str] = None) -> dict:
        cost = QUOTA_COST.get(endpoint, 1)
        url = f"{YOUTUBE_API_BASE}/{endpoint}"

        max_attempts = 2 * len(self.keys)
        for attempt in range(1, max_attempts + 1):
            self._maybe_rollover()
            idx = self._pick_key(cost)
            params = {**params, "key": self.keys[idx]}

            try:
                with httpx.Client(timeout=30.0) as client:
                    r = client.get(url, params=params)
            except httpx.RequestError as ex:
                if attempt < max_attempts:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise RuntimeError(f"Erro de rede em {endpoint}: {ex}") from ex

            if r.status_code == 200:
                self.used[idx] += cost
                self.last_event = {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "label": event_label or endpoint,
                    "cost": cost,
                    "key_index": idx,
                }
                self._persist_state()
                return r.json()

            body = (r.text or "").lower()
            if r.status_code == 403 and ("quota" in body or "daily limit" in body):
                # Key estourou no servidor — marca como esgotada e tenta próxima.
                # Persiste pra próxima request já saber.
                self.used[idx] = self.daily_quota
                self._persist_state()
                continue

            if r.status_code == 400 and "keyinvalid" in body.replace(" ", ""):
                raise InvalidAPIKey(
                    f"API key inválida (índice {idx}). Verifique em /configuracoes."
                )

            if r.status_code in (500, 502, 503, 504):
                if attempt < max_attempts:
                    time.sleep(min(2 ** attempt, 8))
                    continue

            raise RuntimeError(
                f"YouTube API {endpoint} retornou HTTP {r.status_code}: {r.text[:200]}"
            )

        raise RuntimeError(f"YouTube API {endpoint}: esgotadas {max_attempts} tentativas.")

    def search_videos(
        self,
        *,
        query: str,
        published_after_iso: str,
        language: str | None = None,
        max_results: int = 50,
        page_token: str | None = None,
        event_label: Optional[str] = None,
    ) -> dict:
        params = {
            "part": "id,snippet",
            "type": "video",
            "q": query,
            "maxResults": max_results,
            "publishedAfter": published_after_iso,
            "order": "viewCount",
        }
        if language:
            params["relevanceLanguage"] = language
        if page_token:
            params["pageToken"] = page_token
        return self._get("search", params, event_label=event_label or f"search '{query}'")

    def videos_by_ids(self, ids: list[str], event_label: Optional[str] = None) -> list[dict]:
        items: list[dict] = []
        # YouTube aceita até 50 IDs por chamada
        for i in range(0, len(ids), 50):
            chunk = ids[i : i + 50]
            data = self._get(
                "videos",
                {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk)},
                event_label=event_label or f"videos.list ({len(chunk)} ids)",
            )
            items.extend(data.get("items", []))
        return items

    def uploads_playlist_id(self, channel_id: str) -> str:
        """
        Uploads playlist de um canal = channel_id com 'UC' -> 'UU'.
        Truque conhecido da YouTube API que economiza uma chamada a channels.list.
        Funciona desde 2013 e é documentado indiretamente no content_details.
        """
        if channel_id.startswith("UC"):
            return "UU" + channel_id[2:]
        return channel_id  # fallback — raro, mas não quebra

    def playlist_items(
        self, playlist_id: str, max_results: int = 10, event_label: Optional[str] = None
    ) -> list[dict]:
        """Lista os itens mais recentes de uma playlist (ordem já é por data desc)."""
        data = self._get(
            "playlistItems",
            {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": min(max_results, 50),
            },
            event_label=event_label or "playlistItems",
        )
        return data.get("items", [])

    def channels_by_ids(self, ids: list[str], event_label: Optional[str] = None) -> list[dict]:
        items: list[dict] = []
        # Dedup mantendo ordem
        seen: set[str] = set()
        unique = [x for x in ids if not (x in seen or seen.add(x))]
        for i in range(0, len(unique), 50):
            chunk = unique[i : i + 50]
            data = self._get(
                "channels",
                {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk)},
                event_label=event_label or f"channels.list ({len(chunk)} ids)",
            )
            items.extend(data.get("items", []))
        return items

    def resolve_handle(self, handle: str) -> Optional[str]:
        """
        Resolve um handle (`@nome` ou `nome`) para o `UC...` channel ID.
        Custo: 1 unit. Retorna None se não achar.
        """
        h = handle.lstrip("@").strip()
        if not h:
            return None
        data = self._get(
            "channels",
            {"part": "id", "forHandle": f"@{h}"},
            event_label=f"resolve_handle @{h}",
        )
        items = data.get("items") or []
        if items:
            cid = items[0].get("id")
            if cid:
                return str(cid)
        return None


def _load_persisted_usage(db: Session, keys_count: int) -> tuple[list[int], Optional[dict], str]:
    """
    Lê `app_settings.youtube.quota_usage_today` e devolve (used_per_key, last_event, date_utc).
    Aplica rollover diário UTC: se a `date_utc` salva for diferente de hoje, zera
    o vetor de uso e descarta last_event.
    """
    today = _today_utc_str()
    row = db.query(AppSetting).filter_by(key=QUOTA_USAGE_SETTING_KEY).one_or_none()
    if row is None or not row.value:
        return ([0] * keys_count, None, today)
    try:
        payload = json.loads(row.value)
    except (TypeError, ValueError):
        return ([0] * keys_count, None, today)

    saved_date = payload.get("date_utc") or today
    saved_used = payload.get("used_per_key") or []
    saved_event = payload.get("last_event")

    if saved_date != today:
        return ([0] * keys_count, None, today)

    # Normaliza tamanho ao número atual de keys (usuário pode ter
    # adicionado/removido keys entre uma sessão e outra).
    used = [int(v) if isinstance(v, (int, float)) else 0 for v in saved_used]
    used = (used + [0] * keys_count)[:keys_count]
    return (used, saved_event, saved_date)


def build_from_db(db: Session) -> YouTubeClient:
    """Monta o cliente lendo keys cifradas, quota e estado persistido do banco."""
    keys_row = db.query(AppSetting).filter_by(key="youtube.api_keys").one_or_none()
    quota_row = db.query(AppSetting).filter_by(key="youtube.api_key_daily_quota").one_or_none()

    raw_keys: list[str] = []
    if keys_row and keys_row.value:
        decrypted = decrypt(keys_row.value)
        # Aceita keys separadas por vírgula OU quebra de linha (UI usa textarea
        # multilinha; CSV continua funcionando pra compatibilidade).
        raw_keys = [
            k.strip()
            for k in decrypted.replace("\r\n", "\n").replace(",", "\n").split("\n")
            if k.strip()
        ]

    daily_quota = 10000
    if quota_row and quota_row.value:
        try:
            daily_quota = int(quota_row.value)
        except ValueError:
            pass

    used, last_event, date_utc = _load_persisted_usage(db, len(raw_keys))

    return YouTubeClient(
        keys=raw_keys,
        daily_quota=daily_quota,
        used=used,
        db=db,
        date_utc=date_utc,
        last_event=last_event,
    )


def read_quota_summary(db: Session) -> dict:
    """
    Resumo agregado para a central de notificações da UI.

    Não chama o YouTube — só lê `app_settings`. Tolera ausência de keys
    (devolve totais zerados) e estado vazio (nunca consumiu nada hoje).
    """
    keys_row = db.query(AppSetting).filter_by(key="youtube.api_keys").one_or_none()
    quota_row = db.query(AppSetting).filter_by(key="youtube.api_key_daily_quota").one_or_none()

    keys_count = 0
    if keys_row and keys_row.value:
        try:
            decrypted = decrypt(keys_row.value)
            keys_count = sum(
                1
                for k in decrypted.replace("\r\n", "\n").replace(",", "\n").split("\n")
                if k.strip()
            )
        except Exception:  # pragma: no cover
            keys_count = 0

    daily_quota = 10000
    if quota_row and quota_row.value:
        try:
            daily_quota = int(quota_row.value)
        except ValueError:
            pass

    used, last_event, date_utc = _load_persisted_usage(db, keys_count)
    used_total = sum(used)
    total_quota = keys_count * daily_quota
    remaining = max(total_quota - used_total, 0)

    return {
        "date_utc": date_utc,
        "keys_count": keys_count,
        "daily_quota_per_key": daily_quota,
        "total_quota": total_quota,
        "used": used_total,
        "remaining": remaining,
        "used_per_key": used,
        "last_event": last_event,
    }
