"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  apiGet,
  apiPost,
  type ApiVersionResponse,
  type NotificationItem,
  type NotificationsListResponse,
  type NotificationStatus,
  type UnreadCountResponse,
  type YouTubeKeysHealth,
} from "@/lib/api";

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
type LocalKind = "api_offline" | "api_updated";
type LocalNotification = {
  kind: LocalKind;
  // Para api_offline: epoch ms da primeira falha; renderizamos "ha Xs".
  offline_since_ms?: number;
};

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
  const popoverRef = useRef<HTMLDivElement>(null);

  // Pull notifications + counters quando popover abre, ou pull leve só do counter
  // quando fechado. Os dois rodam em background continuamente.
  const loadList = useCallback(async () => {
    try {
      const resp = await apiGet<NotificationsListResponse>(
        "/api/notifications?limit=50",
      );
      setItems(resp.items);
      setUnread(resp.unread_count);
    } catch {
      // silencioso — popover tolera falha; counter continua tentando
    }
  }, []);

  const loadCounter = useCallback(async () => {
    try {
      const resp = await apiGet<UnreadCountResponse>(
        "/api/notifications/unread-count",
      );
      setUnread(resp.unread_count);
    } catch {
      // silencioso — badge tolera falha de rede.
    }
  }, []);

  // Polling do counter (sempre ativo, mesmo com painel fechado).
  useEffect(() => {
    void loadCounter();
    const t = setInterval(loadCounter, POLL_SLOW_MS);
    return () => clearInterval(t);
  }, [loadCounter]);

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

    function setLocal(kind: LocalKind, patch: Partial<LocalNotification> = {}) {
      setLocalNotifs((prev) => {
        const without = prev.filter((n) => n.kind !== kind);
        return [...without, { kind, ...patch }];
      });
    }
    function clearLocal(kind: LocalKind) {
      setLocalNotifs((prev) => prev.filter((n) => n.kind !== kind));
    }

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
  }, []);

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
  // Prioridade: vermelho se ha chave queimada OU API offline; azul se ha
  // notificacoes nao-lidas, redeploy detectado, ou qualquer outra notif local.
  // (A cota agora vive na sidebar — nao influencia o badge aqui.)
  const hasBurned = (health?.burned ?? 0) > 0;
  const hasOfflineLocal = localNotifs.some((n) => n.kind === "api_offline");
  const hasUpdatedLocal = localNotifs.some((n) => n.kind === "api_updated");
  let badgeKind: "danger" | "info" | null = null;
  if (hasBurned || hasOfflineLocal) badgeKind = "danger";
  else if (unread > 0 || hasUpdatedLocal) badgeKind = "info";

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
