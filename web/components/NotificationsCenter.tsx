"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  apiGet,
  apiPost,
  type ApiVersionResponse,
  type NotificationItem,
  type NotificationsListResponse,
  type NotificationStatus,
  type YouTubeKeysHealth,
} from "@/lib/api";
import { useBrowserNotifications } from "@/lib/useBrowserNotifications";

// Polling cadence
const POLL_FAST_MS = 10_000; // popover aberto
const POLL_SLOW_MS = 30_000; // popover fechado (só badge)
const POLL_AMBIENT_MS = 60_000; // health/quota em background
const POLL_VERSION_MS = 60_000; // /api/version pra heartbeat de offline/redeploy
const VERSION_OFFLINE_AFTER_FAILS = 3; // 3 falhas consecutivas = offline
const STARTED_AT_STORAGE_KEY = "app.api.startedAt"; // persiste primeiro started_at observado

// Notificacao local (so existe em state, nao persiste). Sao montadas no
// popover ao lado das notificacoes persistidas. Tipos suportados:
//   - "api_offline": 3+ failures consecutivas no /api/version
//   - "api_updated": started_at mudou desde a primeira leitura
//   - "api_degraded": /api/version ok mas /api/health/ops em erro — banco
//     acessivel mas algum subsistema (scheduler, tabelas, decrypt) caido.
//   - "notifications_unreachable": 3+ falhas seguidas no feed de notificacoes
//     persistidas. O sino fica cego e nada do feed atualiza.
type LocalKind =
  | "api_offline"
  | "api_updated"
  | "api_degraded"
  | "notifications_unreachable";
type LocalNotification = {
  kind: LocalKind;
  // Para api_offline: epoch ms da primeira falha; renderizamos "ha Xs".
  offline_since_ms?: number;
  // Para api_degraded: detalhe vindo de /health/ops (qual check falhou).
  detail?: string;
};

// Polling do /health/ops. Usa o mesmo cadence do version (60s) — barato e
// chega rapido o suficiente.
const POLL_OPS_MS = 60_000;
// Falhas consecutivas em /health/ops para considerar API degradada. Evita
// falso-positivo na janela de startup pos-deploy (api responde antes do
// scheduler/migrations terminarem).
const OPS_DEGRADED_AFTER_FAILS = 2;
// Falhas consecutivas no feed de notificacoes para considerar a central cega.
const NOTIFICATIONS_OFFLINE_AFTER_FAILS = 3;

type HealthOpsCheck = { ok: boolean; detail?: string | null };
type HealthOpsResponse = {
  status: "ok" | "error";
  checks: Record<string, HealthOpsCheck>;
};

// Estado retornado pelo /api/health/ops (tipado para uso fora do polling).
type HealthOpsState = HealthOpsResponse | { error: string } | null;

// =====================================================================
// Helpers de detalhe / copiar
// =====================================================================

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fallback abaixo
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

/**
 * Linha "Ver detalhes ▾ / Copiar" + bloco <pre> com o texto bruto.
 *
 * Usado nos cards de erro (system_alert persistido, ApiDegraded, etc.) para
 * permitir colar o stack na conversa sem poluir o popover quando fechado.
 */
function DetailsToggle({
  label = "Ver detalhes",
  text,
}: {
  label?: string;
  text: string;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  async function onCopy(e: React.MouseEvent) {
    e.stopPropagation();
    const ok = await copyToClipboard(text);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  }

  return (
    <div style={{ marginTop: 6, fontSize: 11 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setOpen((v) => !v);
          }}
          style={{
            background: "transparent",
            border: "none",
            color: "var(--text-dim)",
            cursor: "pointer",
            padding: 0,
            fontSize: 11,
            textDecoration: "underline",
          }}
        >
          {open ? `${label} ▴` : `${label} ▾`}
        </button>
        <button
          type="button"
          onClick={onCopy}
          style={{
            background: "transparent",
            border: "none",
            color: "var(--text-dim)",
            cursor: "pointer",
            padding: 0,
            fontSize: 11,
            textDecoration: "underline",
          }}
        >
          {copied ? "copiado!" : "Copiar"}
        </button>
      </div>
      {open && (
        <pre
          style={{
            marginTop: 6,
            padding: 8,
            background: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: 4,
            fontSize: 10,
            lineHeight: 1.4,
            maxHeight: 240,
            overflow: "auto",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {text}
        </pre>
      )}
    </div>
  );
}

/**
 * Tenta extrair o detalhe técnico (`error`/`traceback`) do `metadata_json` de
 * uma notificação persistente. Retorna texto pronto pra `<DetailsToggle text=...>`.
 * Se não houver `error`/`traceback`, devolve o JSON inteiro como fallback.
 */
function extractItemErrorText(item: NotificationItem): string | null {
  if (!item.metadata_json) return null;
  try {
    const meta = JSON.parse(item.metadata_json) as Record<string, unknown>;
    const errType = typeof meta.error_type === "string" ? meta.error_type : null;
    const errMsg = typeof meta.error === "string" ? meta.error : null;
    const tb = typeof meta.traceback === "string" ? meta.traceback : null;
    const lines: string[] = [];
    if (errType || errMsg) {
      lines.push([errType, errMsg].filter(Boolean).join(": "));
    }
    if (tb) {
      lines.push("");
      lines.push(tb);
    }
    if (lines.length === 0) {
      // Sem campos de erro padrao — mostra o JSON inteiro como fallback util
      // (notificacoes nao-erro tambem podem expor detalhes assim).
      return JSON.stringify(meta, null, 2);
    }
    return lines.join("\n");
  } catch {
    return item.metadata_json;
  }
}

function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const diffMs = Date.now() - then;
  if (diffMs < 0) return "agora";
  const sec = Math.round(diffMs / 1000);
  if (sec < 60) return `há ${sec}s`;
  const min = Math.round(sec / 60);
  if (min < 60) return `há ${min}min`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `há ${hr}h`;
  const day = Math.round(hr / 24);
  return `há ${day}d`;
}

// ---------------------------------------------------------------------------
// Subcomponentes
// ---------------------------------------------------------------------------
const STATUS_COLOR: Record<NotificationStatus, string> = {
  running: "var(--accent)",
  success: "var(--success)",
  error: "var(--danger)",
  info: "var(--text-dim)",
};

function NotificationCard({
  item,
  onRead,
  onDismiss,
}: {
  item: NotificationItem;
  onRead: (id: number) => void;
  onDismiss: (id: number) => void;
}) {
  const isRunning = item.status === "running";
  const unread = item.read_at == null;
  const accent = STATUS_COLOR[item.status] ?? "var(--text-dim)";
  const isSuggestionsChanged = item.type === "suggestions_changed";
  const isViewSpike = item.type === "view_spike";
  // Deep-link do pico: o backend grava `link` no metadata (/analytics?q=...).
  let spikeLink = "/analytics";
  if (isViewSpike && item.metadata_json) {
    try {
      const meta = JSON.parse(item.metadata_json) as { link?: string };
      if (meta.link && meta.link.startsWith("/")) spikeLink = meta.link;
    } catch {
      /* fallback /analytics */
    }
  }
  // Detalhe tecnico (traceback + error_type + repr) so e exposto pra alertas
  // operacionais e erros — em sucesso/progresso/info nao faz sentido. Ainda
  // assim, se houver metadata_json em info, mostramos como fallback.
  const detailText =
    item.status === "error" || item.type === "system_alert"
      ? extractItemErrorText(item)
      : null;

  return (
    <div
      className="notif-card"
      style={{
        borderLeft: `3px solid ${accent}`,
        opacity: unread ? 1 : 0.78,
        cursor: unread ? "pointer" : "default",
      }}
      onClick={() => unread && onRead(item.id)}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 8,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            className="notif-card-title"
            style={{ color: unread ? "var(--text)" : "var(--text-dim)" }}
          >
            {item.title}
          </div>
          {item.message && (
            <div style={{ fontSize: 12, marginTop: 4, color: "var(--text-dim)" }}>
              {item.message}
            </div>
          )}
          {isSuggestionsChanged && (
            <div style={{ marginTop: 6, fontSize: 11 }}>
              <a
                href="/monitoramento?tab=suggestions"
                onClick={(e) => e.stopPropagation()}
              >
                Ver sugestões →
              </a>
            </div>
          )}
          {isViewSpike && (
            <div style={{ marginTop: 6, fontSize: 11 }}>
              <a href={spikeLink} onClick={(e) => e.stopPropagation()}>
                Ver no Analytics →
              </a>
            </div>
          )}
          {detailText && <DetailsToggle text={detailText} />}
          {isRunning && item.progress_pct != null && (
            <div
              aria-label="progresso"
              style={{
                marginTop: 6,
                height: 4,
                borderRadius: 999,
                background: "var(--border)",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${Math.min(100, Math.max(0, item.progress_pct))}%`,
                  height: "100%",
                  background: accent,
                  transition: "width 200ms ease",
                }}
              />
            </div>
          )}
          <div
            className="muted"
            style={{ fontSize: 10, marginTop: 6 }}
          >
            {fmtRelative(item.updated_at)}
          </div>
        </div>
        <button
          type="button"
          aria-label="dispensar notificação"
          onClick={(e) => {
            e.stopPropagation();
            onDismiss(item.id);
          }}
          style={{
            background: "transparent",
            border: "none",
            color: "var(--text-dim)",
            cursor: "pointer",
            fontSize: 16,
            lineHeight: 1,
            padding: "0 4px",
          }}
        >
          ×
        </button>
      </div>
    </div>
  );
}

function ApiOfflineCard({ since }: { since: number }) {
  // Re-render a cada 5s para o "há Xs" subir conforme o tempo passa.
  const [, force] = useState(0);
  useEffect(() => {
    const t = setInterval(() => force((x) => x + 1), 5_000);
    return () => clearInterval(t);
  }, []);
  const elapsedSec = Math.max(0, Math.round((Date.now() - since) / 1000));
  const label =
    elapsedSec < 60
      ? `há ${elapsedSec}s`
      : elapsedSec < 3600
      ? `há ${Math.round(elapsedSec / 60)}min`
      : `há ${Math.round(elapsedSec / 3600)}h`;
  return (
    <div className="notif-card" style={{ borderLeft: "3px solid var(--danger)" }}>
      <div className="notif-card-title" style={{ color: "var(--danger)" }}>
        API offline
      </div>
      <div style={{ fontSize: 12, marginTop: 4 }}>
        Sem resposta {label}. As páginas podem ficar desatualizadas.
      </div>
    </div>
  );
}

function ApiUpdatedCard() {
  return (
    <div className="notif-card" style={{ borderLeft: "3px solid var(--accent)" }}>
      <div className="notif-card-title">API atualizada</div>
      <div style={{ fontSize: 12, marginTop: 4 }}>
        O backend foi atualizado durante esta sessão. Recarregue para pegar a
        versão nova.
      </div>
      <div style={{ marginTop: 8 }}>
        <button
          type="button"
          className="btn-primary"
          onClick={() => window.location.reload()}
          style={{ fontSize: 12, padding: "4px 10px" }}
        >
          Recarregar agora
        </button>
      </div>
    </div>
  );
}

function ApiDegradedCard({
  detail,
  ops,
}: {
  detail?: string;
  ops?: HealthOpsState;
}) {
  // Estado intermediario entre "ok" e "offline": API responde versao mas
  // /health/ops reporta falha em banco/scheduler/decrypt/tabelas.
  // detailsText prioriza ops cru (JSON com todos os checks); cai pra
  // string concatenada se nao houver ops.
  let detailsText: string | null = null;
  if (ops) detailsText = JSON.stringify(ops, null, 2);
  else if (detail) detailsText = detail;
  return (
    <div className="notif-card" style={{ borderLeft: "3px solid var(--danger)" }}>
      <div className="notif-card-title" style={{ color: "var(--danger)" }}>
        API degradada
      </div>
      <div style={{ fontSize: 12, marginTop: 4 }}>
        Algum subsistema do backend está com falha (banco, agendador,
        notificações ou chaves). Algumas telas podem ficar desatualizadas.
      </div>
      {detail && (
        <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
          {detail}
        </div>
      )}
      {detailsText && <DetailsToggle text={detailsText} />}
    </div>
  );
}

function NotificationsUnreachableCard({
  lastError,
}: {
  lastError?: string | null;
}) {
  // Quando o feed de /api/notifications falha repetidamente, o usuario nao
  // tem mais como saber de eventos do backend. O proprio canal de aviso
  // caiu — esse card e a unica coisa que sobra.
  return (
    <div className="notif-card" style={{ borderLeft: "3px solid var(--danger)" }}>
      <div className="notif-card-title" style={{ color: "var(--danger)" }}>
        Central de notificações indisponível
      </div>
      <div style={{ fontSize: 12, marginTop: 4 }}>
        Não foi possível ler notificações do backend. Você pode estar deixando
        de receber avisos de sync, sugestões e falhas operacionais.
      </div>
      {lastError && <DetailsToggle text={lastError} />}
    </div>
  );
}

function BurnedKeysCard({ data }: { data: YouTubeKeysHealth | null }) {
  if (!data || data.burned <= 0) return null;
  return (
    <div className="notif-card" style={{ borderLeft: "3px solid var(--danger)" }}>
      <div className="notif-card-title" style={{ color: "var(--danger)" }}>
        Chave inválida da YouTube API
      </div>
      <div style={{ fontSize: 12, marginTop: 4 }}>
        {data.burned === 1
          ? "1 chave foi marcada como inválida"
          : `${data.burned} chaves foram marcadas como inválidas`}
        {data.last_burned_reason && (
          <span className="muted"> · {data.last_burned_reason}</span>
        )}
      </div>
      {data.last_burned_at && (
        <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
          última: {fmtRelative(data.last_burned_at)}
        </div>
      )}
      <div style={{ marginTop: 8, fontSize: 11 }}>
        <a href="/configuracoes">Ver em Configurações →</a>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------
export function NotificationsCenter() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [health, setHealth] = useState<YouTubeKeysHealth | null>(null);
  const [localNotifs, setLocalNotifs] = useState<LocalNotification[]>([]);
  const versionFailsRef = useRef(0);
  const offlineSinceRef = useRef<number | null>(null);
  // Falhas consecutivas em /api/notifications/* — serve pra mostrar card
  // "Central indisponivel" quando o proprio feed de notificacoes morre.
  const notifFailsRef = useRef(0);
  // Ultimo erro capturado em loadList/loadCounter — exposto no card
  // "Central indisponivel" via DetailsToggle.
  const [notifLastError, setNotifLastError] = useState<string | null>(null);
  // Falhas consecutivas em /api/health/ops — evita card "API degradada"
  // piscar logo apos redeploy enquanto subsistemas terminam de subir.
  const opsFailsRef = useRef(0);
  // Ultimo estado conhecido de /api/health/ops — exposto no card "API
  // degradada" via DetailsToggle (mostra todos os checks cru).
  const [opsState, setOpsState] = useState<HealthOpsState>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const setLocal = useCallback(
    (kind: LocalKind, patch: Partial<LocalNotification> = {}) => {
      setLocalNotifs((prev) => {
        const without = prev.filter((n) => n.kind !== kind);
        return [...without, { kind, ...patch }];
      });
    },
    [],
  );
  const clearLocal = useCallback((kind: LocalKind) => {
    setLocalNotifs((prev) => prev.filter((n) => n.kind !== kind));
  }, []);

  // Conta falhas consecutivas pra detectar "central indisponivel". Ao atingir
  // o threshold, mostra card local; em sucesso volta a zero.
  const onFeedSuccess = useCallback(() => {
    if (notifFailsRef.current >= NOTIFICATIONS_OFFLINE_AFTER_FAILS) {
      clearLocal("notifications_unreachable");
    }
    notifFailsRef.current = 0;
    setNotifLastError(null);
  }, [clearLocal]);

  const onFeedFailure = useCallback(
    (err: unknown) => {
      notifFailsRef.current += 1;
      setNotifLastError(err instanceof Error ? err.message : String(err));
      if (notifFailsRef.current === NOTIFICATIONS_OFFLINE_AFTER_FAILS) {
        setLocal("notifications_unreachable");
      }
    },
    [setLocal],
  );

  // Notificação de navegador para picos de views (type="view_spike").
  // `lastSpikeIdRef === null` na primeira carga: só marca o teto e NÃO notifica
  // (senão todo F5 re-notificaria picos antigos).
  const { send: sendBrowserNotification } = useBrowserNotifications();
  const lastSpikeIdRef = useRef<number | null>(null);
  const notifySpikes = useCallback(
    (list: NotificationItem[]) => {
      const spikes = list.filter((i) => i.type === "view_spike");
      const maxId = spikes.reduce((m, i) => Math.max(m, i.id), 0);
      if (lastSpikeIdRef.current === null) {
        lastSpikeIdRef.current = maxId;
        return;
      }
      const prev = lastSpikeIdRef.current;
      if (maxId <= prev) return;
      for (const s of spikes.filter((i) => i.id > prev)) {
        sendBrowserNotification(s.title, {
          body: s.message ?? undefined,
          tag: `view_spike:${s.id}`,
        });
      }
      lastSpikeIdRef.current = maxId;
    },
    [sendBrowserNotification],
  );

  // Pull da lista completa — roda continuamente (mesmo com painel fechado)
  // porque além do badge ela alimenta a notificação de navegador de picos.
  const loadList = useCallback(async () => {
    try {
      const resp = await apiGet<NotificationsListResponse>(
        "/api/notifications?limit=50",
      );
      setItems(resp.items);
      setUnread(resp.unread_count);
      notifySpikes(resp.items);
      onFeedSuccess();
    } catch (err) {
      onFeedFailure(err);
    }
  }, [notifySpikes, onFeedFailure, onFeedSuccess]);

  // Polling de fundo (painel fechado): lista completa a cada 30s.
  useEffect(() => {
    void loadList();
    const t = setInterval(loadList, POLL_SLOW_MS);
    return () => clearInterval(t);
  }, [loadList]);

  // Polling rápido enquanto painel aberto: traz lista completa.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void (async () => {
      const [, h] = await Promise.all([
        loadList(),
        apiGet<YouTubeKeysHealth>("/api/youtube/keys/health").catch(() => null),
      ]);
      if (cancelled) return;
      if (h) setHealth(h);
    })();
    const t = setInterval(loadList, POLL_FAST_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [open, loadList]);

  // Polling ambiente do health (badge vermelho aparece mesmo com popover fechado).
  useEffect(() => {
    let cancelled = false;
    async function loadHealth() {
      try {
        const resp = await apiGet<YouTubeKeysHealth>("/api/youtube/keys/health");
        if (!cancelled) setHealth(resp);
      } catch {
        // silencioso
      }
    }
    void loadHealth();
    const t = setInterval(loadHealth, POLL_AMBIENT_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  // Heartbeat de /api/version: detecta API offline (3 falhas seguidas) e
  // redeploy (started_at mudou desde a primeira leitura nesta sessao).
  // Notificacoes locais nao persistem — vivem so no state desta sessao.
  useEffect(() => {
    let cancelled = false;

    async function tick() {
      try {
        const resp = await apiGet<ApiVersionResponse>("/api/version");
        if (cancelled) return;

        // Sucesso: sai do estado offline (caso estivesse).
        if (versionFailsRef.current >= VERSION_OFFLINE_AFTER_FAILS) {
          clearLocal("api_offline");
        }
        versionFailsRef.current = 0;
        offlineSinceRef.current = null;

        // Detecta redeploy comparando started_at com o primeiro visto.
        if (resp.started_at) {
          let firstSeen: string | null = null;
          try {
            firstSeen = window.sessionStorage.getItem(STARTED_AT_STORAGE_KEY);
          } catch {
            // sessionStorage indisponivel → roda sem deteccao de redeploy
          }
          if (!firstSeen) {
            try {
              window.sessionStorage.setItem(
                STARTED_AT_STORAGE_KEY,
                resp.started_at,
              );
            } catch {
              /* ignore */
            }
          } else if (firstSeen !== resp.started_at) {
            setLocal("api_updated");
          }
        }
      } catch {
        if (cancelled) return;
        versionFailsRef.current += 1;
        if (versionFailsRef.current === VERSION_OFFLINE_AFTER_FAILS) {
          // marca o instante da PRIMEIRA falha (3 ciclos atras), pra que o
          // contador "ha Xs" reflita o tempo real desde a queda.
          const since = Date.now() - VERSION_OFFLINE_AFTER_FAILS * POLL_VERSION_MS;
          offlineSinceRef.current = since;
          setLocal("api_offline", { offline_since_ms: since });
        }
      }
    }

    void tick();
    const t = setInterval(tick, POLL_VERSION_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [setLocal, clearLocal]);

  // Polling do /api/health/ops: separa "API degradada" (versao OK + ops em
  // erro) de "API offline" (versao nao responde). Quando offline, este check
  // nem importa — o card `api_offline` ja cobre. Quando online com ops em
  // erro, mostra `api_degraded` apontando o subsistema afetado.
  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const resp = await apiGet<HealthOpsResponse>("/api/health/ops");
        if (cancelled) return;
        setOpsState(resp);
        if (resp.status === "ok") {
          opsFailsRef.current = 0;
          clearLocal("api_degraded");
          return;
        }
        // Monta detalhe legivel a partir dos checks falhos.
        const failed: string[] = [];
        for (const [name, check] of Object.entries(resp.checks)) {
          if (!check.ok) {
            failed.push(check.detail ? `${name}: ${check.detail}` : name);
          }
        }
        opsFailsRef.current += 1;
        if (opsFailsRef.current >= OPS_DEGRADED_AFTER_FAILS) {
          setLocal("api_degraded", {
            detail: failed.length
              ? `Subsistema(s): ${failed.join("; ").slice(0, 200)}`
              : undefined,
          });
        }
      } catch (err) {
        // /health/ops respondeu HTTP 503 (esperado quando degradado) — fetch
        // joga error pra status != 2xx. Tambem cai aqui em 404 (api desatualizada
        // sem /api/health/ops) — nao confundir com degradacao real.
        if (cancelled) return;
        setOpsState({
          error: err instanceof Error ? err.message : String(err),
        });
        opsFailsRef.current += 1;
        if (opsFailsRef.current >= OPS_DEGRADED_AFTER_FAILS) {
          setLocal("api_degraded");
        }
      }
    }
    void tick();
    const t = setInterval(tick, POLL_OPS_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [setLocal, clearLocal]);

  // ESC fecha
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Click fora fecha
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (popoverRef.current && !popoverRef.current.contains(target)) {
        setOpen(false);
      }
    };
    const t = setTimeout(() => document.addEventListener("mousedown", onClick), 0);
    return () => {
      clearTimeout(t);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  // ---- ações sobre rows persistidas ----
  async function markRead(id: number) {
    // Optimistic
    setItems((prev) =>
      prev.map((x) =>
        x.id === id && x.read_at == null
          ? { ...x, read_at: new Date().toISOString() }
          : x,
      ),
    );
    setUnread((u) => Math.max(0, u - 1));
    try {
      await apiPost(`/api/notifications/${id}/read`, {});
    } catch {
      // Reverte em caso de falha — recarrega lista pra ficar consistente.
      void loadList();
    }
  }

  async function dismissOne(id: number) {
    const wasUnread = items.find((x) => x.id === id)?.read_at == null;
    setItems((prev) => prev.filter((x) => x.id !== id));
    if (wasUnread) setUnread((u) => Math.max(0, u - 1));
    try {
      await apiPost(`/api/notifications/${id}/dismiss`, {});
    } catch {
      void loadList();
    }
  }

  async function dismissAll() {
    if (items.length === 0) return;
    setItems([]);
    setUnread(0);
    try {
      await apiPost("/api/notifications/dismiss-all", {});
    } catch {
      void loadList();
    }
  }

  // ---- badge ----
  // Prioridade: vermelho se ha chave queimada, API offline, API degradada
  // ou central de notificacoes indisponivel; azul se ha notificacoes nao-lidas
  // ou redeploy detectado.
  // (A cota agora vive na sidebar — nao influencia o badge aqui.)
  const hasBurned = (health?.burned ?? 0) > 0;
  const hasOfflineLocal = localNotifs.some((n) => n.kind === "api_offline");
  const hasDegradedLocal = localNotifs.some((n) => n.kind === "api_degraded");
  const hasNotifsDownLocal = localNotifs.some(
    (n) => n.kind === "notifications_unreachable",
  );
  const hasUpdatedLocal = localNotifs.some((n) => n.kind === "api_updated");
  let badgeKind: "danger" | "info" | null = null;
  if (hasBurned || hasOfflineLocal || hasDegradedLocal || hasNotifsDownLocal) {
    badgeKind = "danger";
  } else if (unread > 0 || hasUpdatedLocal) {
    badgeKind = "info";
  }

  return (
    <div className="notif-root" ref={popoverRef}>
      <button
        type="button"
        className="notif-toggle"
        aria-label="abrir notificações"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden="true">🔔</span>
        {badgeKind && (
          <span
            className={`notif-badge notif-badge-${badgeKind}`}
            aria-hidden="true"
          >
            {unread > 0 ? unread : ""}
          </span>
        )}
      </button>
      {open && (
        <div className="notif-popover" role="dialog" aria-label="Notificações">
          <div
            className="notif-popover-header"
            style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
          >
            <span>Notificações</span>
            {items.length > 0 && (
              <button
                type="button"
                onClick={dismissAll}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--text-dim)",
                  fontSize: 11,
                  cursor: "pointer",
                  padding: 0,
                }}
              >
                Limpar tudo
              </button>
            )}
          </div>
          <div className="notif-popover-body">
            {/* Cards transientes (refletem estado atual, nao evento). Cota
                migrou para a sidebar — aqui ficam alertas de chave queimada
                e os locais de heartbeat (offline / redeploy). */}
            <BurnedKeysCard data={health} />
            {localNotifs.map((n) => {
              if (n.kind === "api_offline") {
                return (
                  <ApiOfflineCard
                    key="api_offline"
                    since={n.offline_since_ms ?? Date.now()}
                  />
                );
              }
              if (n.kind === "api_updated") {
                return <ApiUpdatedCard key="api_updated" />;
              }
              if (n.kind === "api_degraded") {
                return (
                  <ApiDegradedCard
                    key="api_degraded"
                    detail={n.detail}
                    ops={opsState}
                  />
                );
              }
              if (n.kind === "notifications_unreachable") {
                return (
                  <NotificationsUnreachableCard
                    key="notifications_unreachable"
                    lastError={notifLastError}
                  />
                );
              }
              return null;
            })}

            {/* Eventos persistidos */}
            {items.length === 0 ? (
              <div
                className="muted"
                style={{ fontSize: 12, padding: "8px 0" }}
              >
                nenhuma notificação recente.
              </div>
            ) : (
              items.map((it) => (
                <NotificationCard
                  key={it.id}
                  item={it}
                  onRead={markRead}
                  onDismiss={dismissOne}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
