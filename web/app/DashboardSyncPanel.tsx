"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useToast } from "@/components/Toaster";
import { apiGet, apiPost, type SyncRun, type SyncStatus } from "@/lib/api";

type Props = { initial: SyncStatus | null };

function formatDateTime(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function relativeFromNow(s: string | null | undefined): string {
  if (!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return "";
  const diffMs = d.getTime() - Date.now();
  const abs = Math.abs(diffMs);
  const min = Math.round(abs / 60_000);
  const hr = Math.round(abs / 3_600_000);
  const label = diffMs > 0 ? "em" : "há";
  if (hr >= 1) return `${label} ${hr}h`;
  return `${label} ${min}min`;
}

export function DashboardSyncPanel({ initial }: Props) {
  const [status, setStatus] = useState<SyncStatus | null>(initial);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const router = useRouter();

  async function refresh() {
    try {
      const s = await apiGet<SyncStatus>("/api/sync/status");
      setStatus(s);
    } catch (e) {
      toast.error(`Falha ao ler status: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function onRunNow() {
    setBusy(true);
    try {
      const run = await apiPost<SyncRun>("/api/sync/run", {});
      await refresh();
      router.refresh();
      toast.success(
        `Sync concluído: ${run.channels_processed} canais, ${run.videos_processed} vídeos (${run.status}).`
      );
    } catch (e) {
      toast.error(`Falha no sync: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  const last = status?.last_run;
  const next = status?.next_run_at;

  return (
    <div className="card dashboard-sync-panel" style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
      <div>
        <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.4 }}>
          Último sync
        </div>
        <div style={{ fontSize: 14, marginTop: 2 }}>{formatDateTime(last?.started_at)}</div>
        {last && (
          <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
            {last.type} · {last.channels_processed} canais · {last.videos_processed} vídeos ·{" "}
            <span
              className={
                last.status === "success"
                  ? "status-pill"
                  : last.status === "partial"
                  ? "status-pill warn"
                  : "status-pill danger"
              }
              style={{ fontSize: 10 }}
            >
              {last.status}
            </span>
          </div>
        )}
      </div>

      <div className="separator" style={{ width: 1, height: 40, background: "var(--border)" }} />

      <div>
        <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.4 }}>
          Próximo sync automático
        </div>
        <div style={{ fontSize: 14, marginTop: 2 }}>{formatDateTime(next)}</div>
        <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
          {relativeFromNow(next)} · último sync + {status?.interval_hours ?? "?"}h
        </div>
      </div>

      <div className="sync-actions" style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
        <button className="btn-primary" disabled={busy} onClick={onRunNow}>
          {busy ? (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <span className="spinner" aria-hidden />
              Sincronizando…
            </span>
          ) : (
            "Verificar agora"
          )}
        </button>
      </div>
    </div>
  );
}
