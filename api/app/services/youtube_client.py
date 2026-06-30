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

Identidade da key:
  - Cada key recebe uma `fingerprint` = primeiros 16 hex de SHA-256 da string.
  - O JSON persistido usa `used_by_fingerprint: {fp: int}` em vez de vetor por
    posição. Isso preserva o uso correto se o usuário reordenar/remover/adicionar
    keys no meio do dia.
  - Para compatibilidade, ainda lemos o formato antigo `used_per_key: [int]`
    (vetor por posição) e migramos transparentemente.

Concorrência:
  - O persist faz **merge somando deltas** dentro de uma transação curta
    (`SELECT ... FOR UPDATE` na linha do setting), não um overwrite cego.
    Cada `_get` rastreia `pending_delta_by_fp` localmente e flusha pro DB
    somando ao que já estiver lá. Assim duas requests concorrentes em
    processos diferentes não se sobrescrevem.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.core.crypto import decrypt
from app.models import AppSetting

log = logging.getLogger(__name__)

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

# Tamanho do prefixo SHA-256 usado como identidade da key.
# 16 hex = 64 bits — colisão entre as ~poucas keys cadastradas é essencialmente zero
# e o JSON persistido fica curto.
_FP_LEN = 16


class QuotaExceeded(RuntimeError):
    pass


class InvalidAPIKey(RuntimeError):
    pass


class PlaylistNotFound(RuntimeError):
    """
    YouTube respondeu 404 numa playlist (tipicamente a uploads playlist de um
    canal que privou/removeu todos os vídeos). O caller decide o que fazer —
    em `snapshot_channel` vira "canal sem conteúdo → pausar".
    """
    pass


class NoAPIKeyConfigured(RuntimeError):
    pass


class APIKeyDecryptError(RuntimeError):
    """
    Levantada quando `youtube.api_keys` tem valor salvo mas o decrypt falha
    (geralmente APP_SECRET_KEY trocada/perdida). Diferenciada de
    `NoAPIKeyConfigured` para a UI mostrar mensagem específica em vez do
    sintoma genérico "sem chave".
    """
    pass


def _today_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _fingerprint(key: str) -> str:
    """Identidade estável da key sem expor o segredo."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:_FP_LEN]


@dataclass
class YouTubeClient:
    """
    Cliente com rotação automática de keys.

    Não é thread-safe — criar uma instância por request HTTP (via factory
    `build_from_db`), não reutilizar entre requests.

    O contador `used` é hidratado a partir de `app_settings.youtube.quota_usage_today`
    no `build_from_db`, então diferentes processos convergem entre si na próxima
    instância. Toda request bem-sucedida grava o novo estado de volta via merge
    aditivo (não overwrite), preservando consumo de outros processos concorrentes.
    """
    keys: list[str]
    daily_quota: int
    # Identidade estável de cada key, na mesma ordem de `keys`.
    fingerprints: list[str] = field(default_factory=list)
    # Uso por fingerprint (o que está em memória, hidratado do banco no build).
    used_by_fp: dict[str, int] = field(default_factory=dict)
    current: int = 0
    # Sessão DB usada para persistir uso agregado. Opcional: se None, o client
    # funciona normalmente mas sem persistir (modo legado).
    db: Optional[Session] = None
    # Data UTC corrente do estado em memória. Usada pra detectar rollover entre
    # requests dentro do mesmo processo (raro, mas possível com workers longos).
    date_utc: str = field(default_factory=_today_utc_str)
    # Último evento de consumo: {"at": ISO, "label": str, "cost": int, "key_index": int}
    last_event: Optional[dict] = None
    # Deltas locais ainda não somados ao banco — flushados a cada _persist_state.
    # São o que torna o merge entre processos seguro.
    _pending_delta_by_fp: dict[str, int] = field(default_factory=dict)
    # Fingerprints marcadas como esgotadas neste processo (HTTP 403/quota).
    # No merge, o valor final fica saturado em pelo menos `daily_quota` para
    # propagar a saturação aos próximos processos sem inflar o total.
    _pending_exhausted_fp: set[str] = field(default_factory=set)
    # Fingerprints já marcadas como QUEIMADAS no banco (chave inválida/revogada).
    # São completamente ignoradas em `_pick_key`. Hidratado no build_from_db.
    burned_fps: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.keys:
            raise NoAPIKeyConfigured(
                "Nenhuma API key cadastrada. Configure em /configuracoes (youtube.api_keys)."
            )
        if not self.fingerprints or len(self.fingerprints) != len(self.keys):
            self.fingerprints = [_fingerprint(k) for k in self.keys]
        # Garante uma entrada (default 0) para cada fingerprint atual.
        for fp in self.fingerprints:
            self.used_by_fp.setdefault(fp, 0)

    # ---------------------------------------------------------------------
    # Helpers de uso por posição (mantidos para a UI legada / schema atual).
    # ---------------------------------------------------------------------
    @property
    def used(self) -> list[int]:
        """Vetor de uso por posição atual de keys (apenas leitura)."""
        return [int(self.used_by_fp.get(fp, 0)) for fp in self.fingerprints]

    def _remaining(self, idx: int) -> int:
        return self.daily_quota - int(self.used_by_fp.get(self.fingerprints[idx], 0))

    def _pick_key(self, cost: int) -> int:
        n = len(self.keys)
        for offset in range(n):
            idx = (self.current + offset) % n
            fp = self.fingerprints[idx]
            if fp in self.burned_fps:
                continue
            if self._remaining(idx) >= cost:
                self.current = idx
                return idx
        active = n - len(self.burned_fps & set(self.fingerprints))
        if active == 0:
            raise NoAPIKeyConfigured(
                "Todas as chaves estão marcadas como inválidas. "
                "Verifique em /configuracoes."
            )
        raise QuotaExceeded(
            f"Todas as {active} chave(s) ativas atingiram o limite diário ({self.daily_quota})."
        )

    def _maybe_rollover(self) -> None:
        """Se virou o dia em UTC desde o último estado em memória, zera contadores."""
        today = _today_utc_str()
        if today != self.date_utc:
            # Persiste o consumo pendente do dia ANTERIOR antes de zerar — senão
            # deltas já gastos mas ainda não gravados se perdem no rollover
            # (cota subcontada). Tolerante a falha (igual ao _persist_state).
            if self._pending_delta_by_fp or self._pending_exhausted_fp:
                try:
                    self._persist_state()
                except Exception:  # noqa: BLE001
                    pass
            self.date_utc = today
            self.used_by_fp = {fp: 0 for fp in self.fingerprints}
            self._pending_delta_by_fp = {}
            self.last_event = None

    # ---------------------------------------------------------------------
    # Persistência com merge aditivo seguro pra concorrência.
    # ---------------------------------------------------------------------
    def _persist_state(self) -> None:
        """
        Grava o estado atual em `app_settings.youtube.quota_usage_today` como JSON,
        somando deltas locais ao que já estiver no banco (merge aditivo). Isso evita
        que duas execuções concorrentes sobrescrevam o consumo uma da outra.

        Silencioso em falha — o consumo real do YouTube não pode ser bloqueado por
        problema de telemetria.
        """
        if self.db is None:
            return

        # Snapshot dos deltas e marcas de esgotamento pendentes pra esta flush.
        # Mesmo se o evento atual tiver delta zero, o last_event ainda precisa ir
        # pro banco.
        deltas = self._pending_delta_by_fp
        exhausted = self._pending_exhausted_fp
        self._pending_delta_by_fp = {}
        self._pending_exhausted_fp = set()

        try:
            row = (
                self.db.query(AppSetting)
                .filter_by(key=QUOTA_USAGE_SETTING_KEY)
                .with_for_update()
                .one_or_none()
            )

            # Estado atual no banco (sob lock).
            db_used_by_fp: dict[str, int] = {}
            db_date = self.date_utc
            db_last_event = self.last_event
            if row is not None and row.value:
                try:
                    payload = json.loads(row.value)
                    db_date = str(payload.get("date_utc") or self.date_utc)
                    db_used_by_fp = _coerce_used_by_fp(
                        payload, fingerprints=self.fingerprints
                    )
                    if "last_event" in payload:
                        db_last_event = payload.get("last_event")
                except (TypeError, ValueError):
                    db_used_by_fp = {}

            # Rollover: se o que tá no banco é de outro dia (UTC), zera tudo
            # antes de aplicar nossos deltas.
            if db_date != self.date_utc:
                db_used_by_fp = {}
                db_last_event = None

            # Soma os deltas locais sobre o que está no banco (merge aditivo).
            merged: dict[str, int] = dict(db_used_by_fp)
            for fp, delta in deltas.items():
                merged[fp] = int(merged.get(fp, 0)) + int(delta)
            # Keys marcadas como esgotadas neste processo: garantir floor =
            # daily_quota pra propagar a saturação a outros processos sem inflar
            # o total acima do limite.
            for fp in exhausted:
                merged[fp] = max(int(merged.get(fp, 0)), int(self.daily_quota))

            # last_event sempre reflete o evento mais recente conhecido por este
            # processo (o que casa com o comportamento anterior).
            effective_last_event = self.last_event or db_last_event

            # Atualiza memória pra refletir o consenso pós-merge — assim o próximo
            # _pick_key deste processo também vê o que outros processos somaram.
            for fp in self.fingerprints:
                self.used_by_fp[fp] = int(merged.get(fp, 0))
            # Mantém entradas de keys que saíram da config atual (para não perder
            # consumo histórico do dia se o usuário readicionar a key depois).
            for fp, val in merged.items():
                if fp not in self.used_by_fp:
                    self.used_by_fp[fp] = int(val)

            payload_out = {
                "date_utc": self.date_utc,
                "used_by_fingerprint": {fp: int(v) for fp, v in merged.items()},
                "last_event": effective_last_event,
            }
            value = json.dumps(payload_out, separators=(",", ":"))

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
            # Não derruba a request por causa de telemetria. Devolve os deltas
            # pra fila local pra tentar de novo na próxima request.
            log.warning(
                "[youtube_client] falha ao persistir quota_usage_today: %s",
                exc,
                exc_info=True,
            )
            for fp, delta in deltas.items():
                self._pending_delta_by_fp[fp] = (
                    self._pending_delta_by_fp.get(fp, 0) + int(delta)
                )
            self._pending_exhausted_fp |= exhausted
            try:
                self.db.rollback()
            except Exception:
                pass
            # Cria/atualiza alerta operacional sob source_key fixo. Tolera
            # falha — se o canal de notificacoes tambem estiver quebrado, o
            # log estruturado acima ja registrou.
            try:
                from app.services import notifications_service

                notifications_service.safe_system_alert(
                    self.db,
                    source_key="ops:quota_persist_failed",
                    title="Cota da YouTube API: gravação degradada",
                    message=(
                        "Falha ao persistir consumo agregado da cota. "
                        "O widget da sidebar pode mostrar valor desatualizado "
                        "até a próxima gravação bem-sucedida."
                    ),
                    exc=exc,
                )
            except Exception:
                pass

    def flush(self) -> None:
        """
        Persiste deltas de consumo ainda pendentes. Chamar ao FIM de um lote
        de chamadas (ex.: um run de sync que reutiliza o mesmo client) para
        garantir que a última gravação não fique pendente e o consumo não se
        perca quando o objeto for descartado. Tolerante a falha (igual ao
        `_persist_state`).
        """
        self._persist_state()

    def _record_consumption(self, idx: int, cost: int, label: str) -> None:
        fp = self.fingerprints[idx]
        self.used_by_fp[fp] = int(self.used_by_fp.get(fp, 0)) + cost
        self._pending_delta_by_fp[fp] = self._pending_delta_by_fp.get(fp, 0) + cost
        self.last_event = {
            "at": datetime.now(timezone.utc).isoformat(),
            "label": label,
            "cost": cost,
            "key_index": idx,
        }

    def _mark_key_exhausted(self, idx: int) -> None:
        """
        Marca a key como esgotada (HTTP 403/quota). Não conta como delta de
        consumo, mas o merge garante que a fingerprint sai do flush com pelo
        menos `daily_quota` units, propagando a saturação a outros processos.
        """
        fp = self.fingerprints[idx]
        self.used_by_fp[fp] = self.daily_quota
        self._pending_exhausted_fp.add(fp)

    def _mark_key_burned(self, fp: str, *, reason: str) -> None:
        """
        Marca a chave como queimada no banco (persistente, sobrevive a
        reinício) e ignora-a no `_pick_key` deste processo daqui pra frente.
        Tolerante a falha de DB — não bloqueia a request.
        """
        self.burned_fps.add(fp)
        if self.db is None:
            return
        try:
            # Import tardio para evitar ciclo (service usa AppSetting daqui).
            from app.services import youtube_keys_service

            youtube_keys_service.mark_burned(self.db, fp, reason=reason, label=reason)
        except Exception as exc:  # pragma: no cover
            log.warning(
                "[youtube_client] falha ao persistir queimada de %s: %s",
                fp,
                exc,
                exc_info=True,
            )
            try:
                self.db.rollback()
            except Exception:
                pass
            # Sem persistir, o card vermelho de "chave queimada" pode nao
            # aparecer e o cliente vai continuar tentando rotacionar nessa
            # chave em outros processos. Vira alerta operacional.
            try:
                from app.services import notifications_service

                notifications_service.safe_system_alert(
                    self.db,
                    source_key="ops:burned_key_persist_failed",
                    title="Marca de chave queimada não foi salva",
                    message=(
                        f"Uma chave da YouTube API foi rejeitada ({reason}), "
                        "mas não foi possível persistir o estado. Outros "
                        "processos podem continuar tentando essa chave."
                    ),
                    metadata={"fingerprint": fp, "reason": reason},
                    exc=exc,
                )
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
                self._record_consumption(idx, cost, event_label or endpoint)
                self._persist_state()
                return r.json()

            body = (r.text or "").lower()
            if r.status_code == 403 and ("quota" in body or "daily limit" in body):
                # Key estourou no servidor — marca como esgotada e tenta próxima.
                # Persiste pra próxima request já saber.
                self._mark_key_exhausted(idx)
                self._persist_state()
                continue

            if r.status_code == 400 and "keyinvalid" in body.replace(" ", ""):
                # Em vez de explodir a request, marca a chave como QUEIMADA e
                # rotaciona pra próxima. O usuário descobre via central de
                # notificações + tela de Configurações > API do YouTube, e
                # corrige no console do Google quando puder.
                fp = self.fingerprints[idx]
                self._mark_key_burned(fp, reason="keyInvalid")
                if attempt < max_attempts:
                    continue
                raise NoAPIKeyConfigured(
                    "Chave inválida e nenhuma outra disponível. "
                    "Verifique em /configuracoes."
                )

            if r.status_code in (500, 502, 503, 504):
                if attempt < max_attempts:
                    time.sleep(min(2 ** attempt, 8))
                    continue

            # 404 em playlist = uploads playlist inexistente (canal sem vídeos
            # públicos). Exceção específica pra o caller pausar o canal em vez
            # de tratar como erro genérico que quebra o sync toda rodada.
            if r.status_code == 404 and "playlist" in body:
                raise PlaylistNotFound(
                    f"Playlist não encontrada em {endpoint}: {r.text[:200]}"
                )

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


def _coerce_used_by_fp(payload: dict, fingerprints: list[str]) -> dict[str, int]:
    """
    Lê o uso persistido em qualquer um dos formatos suportados:

    Formato novo (preferencial):
        {"used_by_fingerprint": {"<fp>": <int>, ...}}

    Formato antigo (compatibilidade):
        {"used_per_key": [<int>, <int>, ...]}    (posicional)

    No formato antigo, mapeamos posição → fingerprint atual. Se o tamanho não
    bater, perdemos o que sobra — fail-safe pra não atribuir consumo a key errada.
    """
    new = payload.get("used_by_fingerprint")
    if isinstance(new, dict):
        out: dict[str, int] = {}
        for k, v in new.items():
            try:
                out[str(k)] = int(v)
            except (TypeError, ValueError):
                continue
        return out

    legacy = payload.get("used_per_key")
    if isinstance(legacy, list):
        out = {}
        for i, v in enumerate(legacy):
            if i >= len(fingerprints):
                break
            try:
                out[fingerprints[i]] = int(v)
            except (TypeError, ValueError):
                continue
        return out

    return {}


def _load_persisted_state(
    db: Session, fingerprints: list[str]
) -> tuple[dict[str, int], Optional[dict], str]:
    """
    Lê `app_settings.youtube.quota_usage_today` e devolve
    (used_by_fp, last_event, date_utc).

    Aplica rollover diário UTC: se a `date_utc` salva for diferente de hoje, zera
    o uso e descarta last_event. Aceita formato novo (`used_by_fingerprint`) e
    o formato antigo (`used_per_key` posicional) para compatibilidade.
    """
    today = _today_utc_str()
    row = db.query(AppSetting).filter_by(key=QUOTA_USAGE_SETTING_KEY).one_or_none()
    if row is None or not row.value:
        return ({}, None, today)
    try:
        payload = json.loads(row.value)
    except (TypeError, ValueError):
        return ({}, None, today)

    saved_date = str(payload.get("date_utc") or today)
    if saved_date != today:
        return ({}, None, today)

    used_by_fp = _coerce_used_by_fp(payload, fingerprints=fingerprints)
    last_event = payload.get("last_event")
    return (used_by_fp, last_event, saved_date)


def _decrypt_keys_from_db(db: Session) -> list[str]:
    """
    Decifra `youtube.api_keys`. Diferencia:
      - row ausente/vazia        → retorna [] ("sem chave configurada")
      - decrypt falha            → levanta APIKeyDecryptError (config inválida)

    Antes engolíamos qualquer falha de decrypt e retornávamos [], o que mostrava
    "sem chave" pro usuário mesmo quando o problema era APP_SECRET_KEY trocada
    — mascarava a causa real.
    """
    keys_row = db.query(AppSetting).filter_by(key="youtube.api_keys").one_or_none()
    if not (keys_row and keys_row.value):
        return []
    try:
        decrypted = decrypt(keys_row.value)
    except Exception as exc:  # pragma: no cover
        log.warning(
            "[youtube_client] decrypt de youtube.api_keys falhou: %s", exc, exc_info=True
        )
        raise APIKeyDecryptError(
            "Não foi possível decifrar as chaves do YouTube. "
            "APP_SECRET_KEY pode ter sido alterada ou estar incorreta."
        ) from exc
    # Aceita keys separadas por vírgula OU quebra de linha (UI usa textarea
    # multilinha; CSV continua funcionando pra compatibilidade).
    return [
        k.strip()
        for k in decrypted.replace("\r\n", "\n").replace(",", "\n").split("\n")
        if k.strip()
    ]


def _read_daily_quota(db: Session) -> int:
    quota_row = db.query(AppSetting).filter_by(key="youtube.api_key_daily_quota").one_or_none()
    if quota_row and quota_row.value:
        try:
            return int(quota_row.value)
        except ValueError:
            pass
    return 10000


def build_from_db(db: Session) -> YouTubeClient:
    """Monta o cliente lendo keys cifradas, quota e estado persistido do banco."""
    # Import tardio: youtube_keys_service depende deste módulo via AppSetting,
    # então só importamos quando o cliente é construído (sem ciclo de import-time).
    from app.services import youtube_keys_service

    raw_keys = _decrypt_keys_from_db(db)
    daily_quota = _read_daily_quota(db)
    fingerprints = [_fingerprint(k) for k in raw_keys]
    burned_fps = youtube_keys_service.list_burned_fingerprints(db)

    used_by_fp, last_event, date_utc = _load_persisted_state(db, fingerprints)

    return YouTubeClient(
        keys=raw_keys,
        daily_quota=daily_quota,
        fingerprints=fingerprints,
        used_by_fp=dict(used_by_fp),
        db=db,
        date_utc=date_utc,
        last_event=last_event,
        burned_fps=set(burned_fps),
    )


def read_quota_summary(db: Session) -> dict:
    """
    Resumo agregado para a central de notificações da UI.

    Não chama o YouTube — só lê `app_settings`. Tolera ausência de keys
    (devolve totais zerados) e estado vazio (nunca consumiu nada hoje).

    Mantém `used_per_key` no retorno (vetor por posição atual de keys) por
    compatibilidade com o schema/UI; somatório `used` inclui consumo de keys
    eventualmente removidas hoje, pra não esconder gasto real.
    """
    # Falha de decrypt é diagnóstico (config inválida), não falta de chave.
    # Aqui trata como "sem chaves visíveis" pra o widget de cota desenhar zeros
    # em vez de quebrar — o card específico vem de quem realmente tenta usar
    # a API (build_from_db).
    try:
        raw_keys = _decrypt_keys_from_db(db)
    except APIKeyDecryptError:
        raw_keys = []
    fingerprints = [_fingerprint(k) for k in raw_keys]
    keys_count = len(raw_keys)
    daily_quota = _read_daily_quota(db)

    used_by_fp, last_event, date_utc = _load_persisted_state(db, fingerprints)

    used_per_key = [int(used_by_fp.get(fp, 0)) for fp in fingerprints]
    used_total = sum(int(v) for v in used_by_fp.values())
    total_quota = keys_count * daily_quota
    remaining = max(total_quota - sum(used_per_key), 0)

    return {
        "date_utc": date_utc,
        "keys_count": keys_count,
        "daily_quota_per_key": daily_quota,
        "total_quota": total_quota,
        "used": used_total,
        "remaining": remaining,
        "used_per_key": used_per_key,
        "last_event": last_event,
    }
