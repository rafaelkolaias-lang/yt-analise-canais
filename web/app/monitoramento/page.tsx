import {
  apiGet,
  type MonitoredChannel,
  type MonitoredVideo,
} from "@/lib/api";

import { MonitoramentoView } from "./MonitoramentoView";

export const dynamic = "force-dynamic";

type LoadResult =
  | { ok: true; channels: MonitoredChannel[]; videos: MonitoredVideo[] }
  | { ok: false; error: string };

async function loadAll(): Promise<LoadResult> {
  try {
    const [channels, videos] = await Promise.all([
      apiGet<MonitoredChannel[]>("/api/monitoring/channels"),
      apiGet<MonitoredVideo[]>("/api/monitoring/videos"),
    ]);
    return { ok: true, channels, videos };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export default async function MonitoramentoPage() {
  const result = await loadAll();

  return (
    <>
      <header className="page-header">
        <h2>Monitoramento</h2>
        <p className="muted">
          Canais e vídeos que o sistema está acompanhando. Use{" "}
          <strong>Atualizar agora</strong> para gerar um snapshot imediato (puxa do
          YouTube e detecta o melhor upload recente do canal).
        </p>
      </header>

      {result.ok ? (
        <MonitoramentoView
          initialChannels={result.channels}
          initialVideos={result.videos}
        />
      ) : (
        <div className="card">
          <span className="status-pill danger">API offline</span>
          <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
            Suba o backend em <code>localhost:8000</code>.
          </p>
          <p className="muted" style={{ marginTop: 6, fontSize: 11 }}>
            Detalhe: {result.error}
          </p>
        </div>
      )}
    </>
  );
}
