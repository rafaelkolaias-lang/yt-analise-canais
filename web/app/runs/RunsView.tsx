"use client";

import { useState } from "react";

import { useToast } from "@/components/Toaster";
import {
  apiGet,
  apiPatch,
  apiPost,
  type DiscoveryRun,
  type DiscoveryRunWithProgress,
  type MonitoredChannel,
  type MonitoredVideo,
  type ResultChannel,
  type ResultVideo,
  type SyncRun,
} from "@/lib/api";

type Tab = "sync" | "discovery";

type Props = {
  syncRuns: SyncRun[];
  discoveryRuns: DiscoveryRunWithProgress[];
};

function formatDT(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function duration(start: string, end: string | null): string {
  if (!end) return "em andamento";
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  if (!Number.isFinite(s) || !Number.isFinite(e)) return "—";
  const sec = Math.max(0, Math.round((e - s) / 1000));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const rs = sec % 60;
  return `${m}m${rs}s`;
}

function formatInt(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("pt-BR");
}

function StatusPill({ status }: { status: string }) {
  const cls =
    status === "success"
      ? "status-pill"
      : status === "partial" || status === "running"
      ? "status-pill warn"
      : "status-pill danger";
  return (
    <span className={cls} style={{ fontSize: 10 }}>
      {status}
    </span>
  );
}

function progressLabel(p: { total: number; reviewed: number }): string {
  if (p.total === 0) return "—";
  const pct = Math.round((p.reviewed / p.total) * 100);
  return `${p.reviewed}/${p.total} (${pct}%)`;
}

export function RunsView({ syncRuns, discoveryRuns: initialDiscoveryRuns }: Props) {
  const [tab, setTab] = useState<Tab>("sync");
  const [discoveryRuns, setDiscoveryRuns] = useState(initialDiscoveryRuns);
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null);
  const [runDetail, setRunDetail] = useState<DiscoveryRun | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const toast = useToast();

  async function openRun(runId: number) {
    if (expandedRunId === runId) {
      setExpandedRunId(null);
      setRunDetail(null);
      return;
    }
    setExpandedRunId(runId);
    setRunDetail(null);
    setLoadingDetail(true);
    try {
      const detail = await apiGet<DiscoveryRun>(`/api/discovery/runs/${runId}`);
      setRunDetail(detail);
    } catch (e) {
      toast.error(`Falha ao carregar run: ${e instanceof Error ? e.message : String(e)}`);
      setExpandedRunId(null);
    } finally {
      setLoadingDetail(false);
    }
  }

  function applyDetailLocally(updater: (d: DiscoveryRun) => DiscoveryRun) {
    setRunDetail((d) => (d ? updater(d) : d));
  }

  function bumpProgress(runId: number, delta: { channels?: number; videos?: number }) {
    setDiscoveryRuns((prev) =>
      prev.map((r) =>
        r.id === runId
          ? {
              ...r,
              progress: {
                ...r.progress,
                channels_reviewed:
                  r.progress.channels_reviewed + (delta.channels ?? 0),
                videos_reviewed:
                  r.progress.videos_reviewed + (delta.videos ?? 0),
              },
            }
          : r
      )
    );
  }

  async function toggleChannelReview(c: ResultChannel) {
    if (!runDetail) return;
    const wasReviewed = c.reviewed_at != null;
    const next = !wasReviewed;
    try {
      const resp = await apiPatch<{ reviewed_at: string | null }>(
        `/api/discovery/runs/${runDetail.id}/channels/${c.id}/review`,
        { reviewed: next }
      );
      applyDetailLocally((d) => ({
        ...d,
        channel_results: d.channel_results.map((x) =>
          x.id === c.id ? { ...x, reviewed_at: resp.reviewed_at } : x
        ),
      }));
      bumpProgress(runDetail.id, { channels: next ? 1 : -1 });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  }

  async function toggleVideoReview(v: ResultVideo) {
    if (!runDetail) return;
    const wasReviewed = v.reviewed_at != null;
    const next = !wasReviewed;
    try {
      const resp = await apiPatch<{ reviewed_at: string | null }>(
        `/api/discovery/runs/${runDetail.id}/videos/${v.id}/review`,
        { reviewed: next }
      );
      applyDetailLocally((d) => ({
        ...d,
        video_results: d.video_results.map((x) =>
          x.id === v.id ? { ...x, reviewed_at: resp.reviewed_at } : x
        ),
      }));
      bumpProgress(runDetail.id, { videos: next ? 1 : -1 });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  }

  async function addChannel(c: ResultChannel) {
    try {
      await apiPost<MonitoredChannel>("/api/monitoring/channels", {
        youtube_channel_id: c.youtube_channel_id,
      });
      toast.success(`Monitorando "${c.title}".`);
      // Adicionar ao monitoramento implica que o item foi triado.
      if (c.reviewed_at == null) await toggleChannelReview(c);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  }

  async function addVideo(v: ResultVideo) {
    try {
      await apiPost<MonitoredVideo>("/api/monitoring/videos", {
        youtube_video_id: v.youtube_video_id,
      });
      toast.success("Vídeo adicionado ao monitoramento.");
      if (v.reviewed_at == null) await toggleVideoReview(v);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="tabs">
        <button
          className={tab === "sync" ? "tab active" : "tab"}
          onClick={() => setTab("sync")}
        >
          Sync <span className="tab-count">{syncRuns.length}</span>
        </button>
        <button
          className={tab === "discovery" ? "tab active" : "tab"}
          onClick={() => setTab("discovery")}
        >
          Descoberta <span className="tab-count">{discoveryRuns.length}</span>
        </button>
      </div>

      {tab === "sync" && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>Tipo</th>
                <th>Status</th>
                <th>Iniciado</th>
                <th>Duração</th>
                <th style={{ textAlign: "right" }}>Canais</th>
                <th style={{ textAlign: "right" }}>Vídeos</th>
                <th>Observações</th>
              </tr>
            </thead>
            <tbody>
              {syncRuns.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td className="muted" style={{ fontSize: 11 }}>{r.type}</td>
                  <td><StatusPill status={r.status} /></td>
                  <td style={{ fontSize: 11 }}>{formatDT(r.started_at)}</td>
                  <td style={{ fontSize: 11 }}>{duration(r.started_at, r.finished_at)}</td>
                  <td style={{ textAlign: "right" }}>{r.channels_processed}</td>
                  <td style={{ textAlign: "right" }}>{r.videos_processed}</td>
                  <td className="muted" style={{ fontSize: 11, maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.notes ?? undefined}>
                    {r.notes ?? "—"}
                  </td>
                </tr>
              ))}
              {syncRuns.length === 0 && (
                <tr>
                  <td colSpan={8} className="muted" style={{ textAlign: "center", padding: 16 }}>
                    nenhum sync ainda. Vá ao <a href="/">Dashboard</a> e clique em Verificar agora.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === "discovery" && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 36 }}></th>
                <th>#</th>
                <th>Termos</th>
                <th>Status</th>
                <th>Iniciado</th>
                <th>Duração</th>
                <th style={{ textAlign: "right" }}>Canais</th>
                <th style={{ textAlign: "right" }}>Vídeos</th>
                <th>Revisão (canais)</th>
                <th>Revisão (vídeos)</th>
              </tr>
            </thead>
            <tbody>
              {discoveryRuns.map((r) => {
                const isOpen = expandedRunId === r.id;
                return (
                  <>
                    <tr
                      key={r.id}
                      className={isOpen ? "row-selected" : ""}
                      style={{ cursor: "pointer" }}
                      onClick={() => openRun(r.id)}
                    >
                      <td style={{ textAlign: "center", fontSize: 11 }}>
                        {isOpen ? "▾" : "▸"}
                      </td>
                      <td>{r.id}</td>
                      <td style={{ maxWidth: 380, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.terms}>
                        {r.terms}
                      </td>
                      <td><StatusPill status={r.status} /></td>
                      <td style={{ fontSize: 11 }}>{formatDT(r.started_at)}</td>
                      <td style={{ fontSize: 11 }}>{duration(r.started_at, r.finished_at)}</td>
                      <td style={{ textAlign: "right" }}>{r.channels_found}</td>
                      <td style={{ textAlign: "right" }}>{r.videos_found}</td>
                      <td style={{ fontSize: 11 }}>
                        {progressLabel({
                          total: r.progress.channels_total,
                          reviewed: r.progress.channels_reviewed,
                        })}
                      </td>
                      <td style={{ fontSize: 11 }}>
                        {progressLabel({
                          total: r.progress.videos_total,
                          reviewed: r.progress.videos_reviewed,
                        })}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr key={`${r.id}-detail`}>
                        <td colSpan={10} style={{ background: "var(--bg)" }}>
                          {loadingDetail || !runDetail ? (
                            <div className="muted" style={{ padding: 12, fontSize: 12 }}>
                              carregando detalhes…
                            </div>
                          ) : (
                            <RunDetail
                              run={runDetail}
                              onToggleChannel={toggleChannelReview}
                              onToggleVideo={toggleVideoReview}
                              onAddChannel={addChannel}
                              onAddVideo={addVideo}
                            />
                          )}
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
              {discoveryRuns.length === 0 && (
                <tr>
                  <td colSpan={10} className="muted" style={{ textAlign: "center", padding: 16 }}>
                    nenhuma busca ainda. <a href="/descoberta">Rode uma em Descoberta</a>.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RunDetail({
  run,
  onToggleChannel,
  onToggleVideo,
  onAddChannel,
  onAddVideo,
}: {
  run: DiscoveryRun;
  onToggleChannel: (c: ResultChannel) => void;
  onToggleVideo: (v: ResultVideo) => void;
  onAddChannel: (c: ResultChannel) => void;
  onAddVideo: (v: ResultVideo) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, padding: 12 }}>
      {run.channel_results.length > 0 && (
        <div>
          <h4 style={{ margin: "0 0 6px", fontSize: 13 }}>
            Canais{" "}
            <span className="muted" style={{ fontWeight: 400, fontSize: 11 }}>
              ({run.progress.channels_reviewed}/{run.progress.channels_total} revisados)
            </span>
          </h4>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 36 }}>OK</th>
                  <th>Canal</th>
                  <th style={{ textAlign: "right" }}>Inscritos</th>
                  <th style={{ textAlign: "right" }}>Vídeos</th>
                  <th style={{ textAlign: "right" }}>Views totais</th>
                  <th style={{ width: 140 }}></th>
                </tr>
              </thead>
              <tbody>
                {run.channel_results.map((c) => {
                  const reviewed = c.reviewed_at != null;
                  return (
                    <tr key={c.id} style={{ opacity: reviewed ? 0.65 : 1 }}>
                      <td style={{ textAlign: "center" }}>
                        <input
                          type="checkbox"
                          checked={reviewed}
                          onChange={() => onToggleChannel(c)}
                          aria-label={`marcar ${c.title} como revisado`}
                        />
                      </td>
                      <td>
                        <a href={c.url ?? "#"} target="_blank" rel="noreferrer">
                          {c.title}
                        </a>
                      </td>
                      <td style={{ textAlign: "right" }}>{formatInt(c.subscribers)}</td>
                      <td style={{ textAlign: "right" }}>{formatInt(c.video_count)}</td>
                      <td style={{ textAlign: "right" }}>{formatInt(c.views_total)}</td>
                      <td>
                        <button
                          type="button"
                          className="btn-ghost"
                          onClick={() => onAddChannel(c)}
                        >
                          Monitorar
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {run.video_results.length > 0 && (
        <div>
          <h4 style={{ margin: "0 0 6px", fontSize: 13 }}>
            Vídeos{" "}
            <span className="muted" style={{ fontWeight: 400, fontSize: 11 }}>
              ({run.progress.videos_reviewed}/{run.progress.videos_total} revisados)
            </span>
          </h4>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 36 }}>OK</th>
                  <th>Título</th>
                  <th style={{ textAlign: "right" }}>Views</th>
                  <th style={{ textAlign: "right" }}>VPD</th>
                  <th>Termo</th>
                  <th style={{ width: 140 }}></th>
                </tr>
              </thead>
              <tbody>
                {run.video_results.map((v) => {
                  const reviewed = v.reviewed_at != null;
                  return (
                    <tr key={v.id} style={{ opacity: reviewed ? 0.65 : 1 }}>
                      <td style={{ textAlign: "center" }}>
                        <input
                          type="checkbox"
                          checked={reviewed}
                          onChange={() => onToggleVideo(v)}
                          aria-label={`marcar vídeo como revisado`}
                        />
                      </td>
                      <td>
                        <a href={v.url ?? "#"} target="_blank" rel="noreferrer">
                          {v.title}
                        </a>
                      </td>
                      <td style={{ textAlign: "right" }}>{formatInt(v.views)}</td>
                      <td style={{ textAlign: "right" }}>
                        {v.vpd != null ? formatInt(Math.round(v.vpd)) : "—"}
                      </td>
                      <td className="muted" style={{ fontSize: 11 }}>
                        {v.matched_term ?? "—"}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-ghost"
                          onClick={() => onAddVideo(v)}
                        >
                          Monitorar
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {run.channel_results.length === 0 && run.video_results.length === 0 && (
        <div className="muted" style={{ fontSize: 12 }}>
          nenhum resultado nesse run.
        </div>
      )}
    </div>
  );
}
