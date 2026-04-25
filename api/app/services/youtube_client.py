"""
Cliente YouTube Data API v3 — httpx sync, com rotação de keys.

Responsabilidades:
  - Ler `youtube.api_keys` (CSV cifrado) do banco e decifrar.
  - Rotacionar keys quando uma estoura quota (HTTP 403 + 'quota'/'forbidden').
  - Contar custo por request (tabela `QUOTA_COST`) contra `youtube.api_key_daily_quota`.
  - Expor search/videos/channels como funções simples que já fazem a retentativa.

Convenções:
  - NÃO mantém contadores entre processos (é memória do processo atual). Pra quota
    precisa atravessar deploys, mover pra `app_settings` no futuro.
  - Se nenhuma key tem saldo, levanta `QuotaExceeded`.
  - Se key é inválida (HTTP 400 keyInvalid), levanta `InvalidAPIKey`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

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


class QuotaExceeded(RuntimeError):
    pass


class InvalidAPIKey(RuntimeError):
    pass


class NoAPIKeyConfigured(RuntimeError):
    pass


@dataclass
class YouTubeClient:
    """
    Cliente com rotação automática de keys.

    Não é thread-safe — criar uma instância por request HTTP (via factory
    `build_from_db`), não reutilizar entre requests.
    """
    keys: list[str]
    daily_quota: int
    used: list[int] = field(default_factory=list)
    current: int = 0

    def __post_init__(self) -> None:
        if not self.keys:
            raise NoAPIKeyConfigured(
                "Nenhuma API key cadastrada. Configure em /configuracoes (youtube.api_keys)."
            )
        if len(self.used) != len(self.keys):
            self.used = [0] * len(self.keys)

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

    def _get(self, endpoint: str, params: dict) -> dict:
        cost = QUOTA_COST.get(endpoint, 1)
        url = f"{YOUTUBE_API_BASE}/{endpoint}"

        max_attempts = 2 * len(self.keys)
        for attempt in range(1, max_attempts + 1):
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
                return r.json()

            body = (r.text or "").lower()
            if r.status_code == 403 and ("quota" in body or "daily limit" in body):
                # Key estourou no servidor — marca como esgotada e tenta próxima
                self.used[idx] = self.daily_quota
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
        return self._get("search", params)

    def videos_by_ids(self, ids: list[str]) -> list[dict]:
        items: list[dict] = []
        # YouTube aceita até 50 IDs por chamada
        for i in range(0, len(ids), 50):
            chunk = ids[i : i + 50]
            data = self._get(
                "videos",
                {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk)},
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

    def playlist_items(self, playlist_id: str, max_results: int = 10) -> list[dict]:
        """Lista os itens mais recentes de uma playlist (ordem já é por data desc)."""
        data = self._get(
            "playlistItems",
            {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": min(max_results, 50),
            },
        )
        return data.get("items", [])

    def channels_by_ids(self, ids: list[str]) -> list[dict]:
        items: list[dict] = []
        # Dedup mantendo ordem
        seen: set[str] = set()
        unique = [x for x in ids if not (x in seen or seen.add(x))]
        for i in range(0, len(unique), 50):
            chunk = unique[i : i + 50]
            data = self._get(
                "channels",
                {"part": "snippet,statistics,contentDetails", "id": ",".join(chunk)},
            )
            items.extend(data.get("items", []))
        return items


def build_from_db(db: Session) -> YouTubeClient:
    """Monta o cliente lendo keys cifradas e quota do banco."""
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

    return YouTubeClient(keys=raw_keys, daily_quota=daily_quota)
