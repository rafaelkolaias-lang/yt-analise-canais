import {
  API_URL,
  type AnalyticsOverview,
  type MonitoredChannel,
  type MonitoredVideo,
  type SyncStatus,
} from "@/lib/api";

import { DashboardSyncPanel } from "./DashboardSyncPanel";

export const dynamic = "force-dynamic";

async function fetchJSON<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

type HealthInfo = { status: string; app?: string; env?: string };
type DbHealth = { status: string; db?: string; detail?: string };

async function loadAll() {
  const [root, health, db, sync, channels, videos, overview] = await Promise.all([
    fetchJSON<HealthInfo>("/"),
    fetchJSON<HealthInfo>("/health"),
    fetchJSON<DbHealth>("/health/db"),
    fetchJSON<SyncStatus>("/api/sync/status"),
    fetchJSON<MonitoredChannel[]>("/api/monitoring/channels"),
    fetchJSON<MonitoredVideo[]>("/api/monitoring/videos"),
    fetchJSON<AnalyticsOverview>("/api/analytics/overview"),
  ]);
  return { root, health, db, sync, channels, videos, overview };
}

export default async function DashboardPage() {
  const { health, db, sync, channels, videos, overview } = await loadAll();

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

      <section className="card-grid" style={{ marginTop: 16 }}>
        <div className="card">
          <div className="muted">Aquecendo</div>
          <div style={{ fontSize: 22, marginTop: 4 }}>
            {overview?.channels_accelerating ?? "—"}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>
            <a href="/analytics">ver analytics</a>
          </div>
        </div>
        <div className="card">
          <div className="muted">Promissores</div>
          <div style={{ fontSize: 22, marginTop: 4 }}>
            {overview?.channels_promising ?? "—"}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>
            pequenos com VPD alto
          </div>
        </div>
        <div className="card">
          <div className="muted">Saturados</div>
          <div style={{ fontSize: 22, marginTop: 4 }}>
            {overview?.channels_saturated ?? "—"}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>acima do limite</div>
        </div>
        <div className="card">
          <div className="muted">Vídeos acelerando</div>
          <div style={{ fontSize: 22, marginTop: 4 }}>
            {overview?.videos_accelerating ?? "—"}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>
            VPD crescendo no último snapshot
          </div>
        </div>
      </section>
    </>
  );
}
