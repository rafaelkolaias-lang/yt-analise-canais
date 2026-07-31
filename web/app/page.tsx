import {
  API_URL,
  type AnalyticsOverview,
  type MonitoredChannel,
  type MonitoredVideo,
  type SyncRun,
  type SyncStatus,
} from "@/lib/api";
import { serverApiGetOrNull as fetchJSON } from "@/lib/serverApi";

import { DashboardHighlights } from "./DashboardHighlights";
import { DashboardSyncPanel } from "./DashboardSyncPanel";

export const dynamic = "force-dynamic";

type HealthInfo = { status: string; app?: string; env?: string };
type DbHealth = { status: string; db?: string; detail?: string };

async function loadAll() {
  const [root, health, db, sync, channels, videos, overview, runs] = await Promise.all([
    fetchJSON<HealthInfo>("/"),
    fetchJSON<HealthInfo>("/health"),
    fetchJSON<DbHealth>("/health/db"),
    fetchJSON<SyncStatus>("/api/sync/status"),
    fetchJSON<MonitoredChannel[]>("/api/monitoring/channels"),
    fetchJSON<MonitoredVideo[]>("/api/monitoring/videos"),
    fetchJSON<AnalyticsOverview>("/api/analytics/overview"),
    fetchJSON<SyncRun[]>("/api/sync/runs?limit=3"),
  ]);
  return { root, health, db, sync, channels, videos, overview, runs };
}

function formatRunDT(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function runDuration(start: string, end: string | null): string {
  if (!end) return "em andamento";
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  if (!Number.isFinite(s) || !Number.isFinite(e)) return "—";
  const sec = Math.max(0, Math.round((e - s) / 1000));
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m${sec % 60}s`;
}

function runPillClass(status: string): string {
  if (status === "success") return "status-pill";
  if (status === "partial" || status === "running") return "status-pill warn";
  return "status-pill danger";
}

export default async function DashboardPage() {
  const { health, db, sync, channels, videos, overview, runs } = await loadAll();

  const apiOk = health?.status === "ok";
  const dbOk = db?.status === "ok";

  return (
    <>
      <header className="page-header">
        <h2>Dashboard</h2>
        <p className="muted">
          Visão geral do sistema. O sync automático roda em background a cada{" "}
          <strong>{sync?.interval_hours ?? "?"}h</strong>. Use{" "}
          <strong>Verificar agora</strong> para disparar um sync manual imediato.
        </p>
      </header>

      <DashboardSyncPanel initial={sync} />

      <section className="card-grid" style={{ marginTop: 16 }}>
        <div className="card">
          <div className="muted">API</div>
          {apiOk ? (
            <>
              <div style={{ fontSize: 18, marginTop: 4 }}>{health?.app ?? "—"}</div>
              <div style={{ marginTop: 6 }}>
                <span className="status-pill">{health?.status}</span>{" "}
                <span className="muted">env: {health?.env}</span>
              </div>
            </>
          ) : (
            <>
              <div style={{ fontSize: 18, marginTop: 4 }}>offline</div>
              <span className="status-pill danger">erro</span>{" "}
              <span className="muted">subir uvicorn em {API_URL}</span>
            </>
          )}
        </div>

        <div className="card">
          <div className="muted">Banco</div>
          <div style={{ fontSize: 18, marginTop: 4 }}>{db?.db ?? "—"}</div>
          <div style={{ marginTop: 6 }}>
            <span className={dbOk ? "status-pill" : "status-pill danger"}>
              {db?.status ?? "—"}
            </span>
          </div>
          {db?.detail && !dbOk && (
            <div className="muted" style={{ marginTop: 6, fontSize: 11 }}>{db.detail}</div>
          )}
        </div>

        <div className="card">
          <div className="muted">Canais monitorados</div>
          <div style={{ fontSize: 28, marginTop: 4 }}>{channels?.length ?? "—"}</div>
          <div className="muted" style={{ fontSize: 11 }}>
            {channels?.filter((c) => c.status === "active").length ?? "—"} ativos
          </div>
        </div>

        <div className="card">
          <div className="muted">Vídeos monitorados</div>
          <div style={{ fontSize: 28, marginTop: 4 }}>{videos?.length ?? "—"}</div>
          <div className="muted" style={{ fontSize: 11 }}>
            {videos?.filter((v) => v.status === "active").length ?? "—"} ativos
          </div>
        </div>
      </section>

      {/* Últimos 3 runs de sync — resumo compacto do que a página /runs lista. */}
      <section className="card" style={{ marginTop: 16 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
          }}
        >
          <div className="muted">Últimos 3 runs</div>
          <a href="/runs" style={{ fontSize: 12 }}>
            ver todos →
          </a>
        </div>
        {runs && runs.length > 0 ? (
          <div style={{ marginTop: 6 }}>
            {runs.slice(0, 3).map((r) => (
              <div
                key={r.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  flexWrap: "wrap",
                  borderTop: "1px solid var(--border)",
                  padding: "8px 0",
                  fontSize: 12,
                }}
              >
                <span className={runPillClass(r.status)} style={{ fontSize: 10 }}>
                  {r.status}
                </span>
                <span>{r.type === "manual" ? "manual" : "automático"}</span>
                <span className="muted">
                  {formatRunDT(r.started_at)} · {runDuration(r.started_at, r.finished_at)}
                </span>
                <span className="muted" style={{ marginLeft: "auto" }}>
                  {r.channels_processed} canais · {r.videos_processed} vídeos
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            nenhum run registrado ainda
          </div>
        )}
      </section>

      {/* Cada card abre, logo abaixo, a lista compacta do que ele conta. */}
      <DashboardHighlights overview={overview} />
    </>
  );
}
