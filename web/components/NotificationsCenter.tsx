"use client";

import { useEffect, useRef, useState } from "react";

import { apiGet, type QuotaSummary } from "@/lib/api";

// Cada card do painel é independente: para adicionar uma nova notificação no
// futuro basta adicionar mais um item à `cards` lá embaixo. O shell (ícone +
// painel + posicionamento + interações) não precisa ser tocado.
type NotificationCard = {
  id: string;
  render: () => React.ReactNode;
};

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR");
}

function fmtPct(used: number, total: number): string {
  if (total <= 0) return "—";
  return `${((used / total) * 100).toFixed(1)}%`;
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

function QuotaCard({ data, error, loading }: { data: QuotaSummary | null; error: string | null; loading: boolean }) {
  if (loading && !data) {
    return (
      <div className="notif-card">
        <div className="notif-card-title">Cota da YouTube API</div>
        <div className="muted" style={{ fontSize: 12 }}>carregando…</div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="notif-card">
        <div className="notif-card-title">Cota da YouTube API</div>
        <div className="muted" style={{ fontSize: 12, color: "var(--danger)" }}>
          {error}
        </div>
      </div>
    );
  }
  if (!data) return null;

  const noKeys = data.keys_count === 0;
  const pct = data.total_quota > 0 ? (data.used / data.total_quota) * 100 : 0;
  const barColor =
    pct >= 90 ? "var(--danger)" : pct >= 70 ? "var(--warn)" : "var(--success)";

  return (
    <div className="notif-card">
      <div className="notif-card-title">Cota da YouTube API</div>
      {noKeys ? (
        <div className="muted" style={{ fontSize: 12 }}>
          Nenhuma API key cadastrada. Configure em <a href="/configuracoes">Configurações</a>.
        </div>
      ) : (
        <>
          <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
            {data.keys_count} {data.keys_count === 1 ? "key" : "keys"} ·{" "}
            {fmt(data.daily_quota_per_key)} units/dia cada · reset em UTC
          </div>
          <div style={{ marginTop: 8, fontSize: 13 }}>
            <strong>{fmt(data.used)}</strong> usado de{" "}
            <strong>{fmt(data.total_quota)}</strong>
            <span className="muted" style={{ marginLeft: 6 }}>
              ({fmtPct(data.used, data.total_quota)})
            </span>
          </div>
          <div
            style={{
              marginTop: 6,
              height: 6,
              borderRadius: 999,
              background: "var(--border)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${Math.min(pct, 100)}%`,
                height: "100%",
                background: barColor,
                transition: "width 200ms ease",
              }}
            />
          </div>
          <div style={{ marginTop: 6, fontSize: 12, color: "var(--text-dim)" }}>
            restante: <strong>{fmt(data.remaining)}</strong> units
          </div>
          {data.last_event && (
            <div style={{ marginTop: 8, fontSize: 11, color: "var(--text-dim)" }}>
              último evento: <strong>{data.last_event.label}</strong> ·{" "}
              {data.last_event.cost} units · {fmtRelative(data.last_event.at)}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function NotificationsCenter() {
  const [open, setOpen] = useState(false);
  const [quota, setQuota] = useState<QuotaSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Recarrega o quota-summary toda vez que abre, e também a cada 30s enquanto
  // estiver aberto, pra refletir consumo de syncs em background.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const resp = await apiGet<QuotaSummary>("/api/notifications/quota-summary");
        if (!cancelled) setQuota(resp);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    timer = setInterval(load, 30_000);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [open]);

  // ESC fecha o painel.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Click fora do popover fecha.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (popoverRef.current && !popoverRef.current.contains(target)) {
        setOpen(false);
      }
    };
    // Defer para o próximo tick, senão o próprio clique no botão de abrir já fecha.
    const t = setTimeout(() => document.addEventListener("mousedown", onClick), 0);
    return () => {
      clearTimeout(t);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  // Lista de cards. Para adicionar nova notificação no futuro: append aqui.
  const cards: NotificationCard[] = [
    {
      id: "youtube-quota",
      render: () => <QuotaCard data={quota} error={error} loading={loading} />,
    },
  ];

  // Badge no ícone: aparece quando uso ≥ 70% (warn) ou ≥ 90% (danger).
  const pct =
    quota && quota.total_quota > 0 ? (quota.used / quota.total_quota) * 100 : 0;
  const badgeKind = pct >= 90 ? "danger" : pct >= 70 ? "warn" : null;

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
          <span className={`notif-badge notif-badge-${badgeKind}`} aria-hidden="true" />
        )}
      </button>
      {open && (
        <div className="notif-popover" role="dialog" aria-label="Notificações">
          <div className="notif-popover-header">Notificações</div>
          <div className="notif-popover-body">
            {cards.map((c) => (
              <div key={c.id}>{c.render()}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
