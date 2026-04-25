"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AddByLinkInput } from "@/components/AddByLinkInput";
import { ChannelAvatar } from "@/components/ChannelAvatar";
import {
  ChannelsFilterBar,
  DEFAULT_CHANNEL_FILTERS,
  applyChannelFilters,
  type ChannelFilters,
  type ChannelSortKey,
} from "@/components/ChannelsFilterBar";
import { SortableHeader } from "@/components/SortableHeader";
import { useToast } from "@/components/Toaster";
import { VideoThumbnail } from "@/components/VideoThumbnail";
import {
  DEFAULT_VIDEO_FILTERS,
  VideosFilterBar,
  applyVideoFilters,
  type VideoFilters,
  type VideoSortKey,
} from "@/components/VideosFilterBar";
import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  type ChannelSnapshot,
  type MonitoredChannel,
  type MonitoredVideo,
  type VideoSnapshot,
} from "@/lib/api";

type Tab = "channels" | "videos" | "best";
type VideoLayout = "list" | "grid";

const VIDEO_LAYOUT_STORAGE_KEY = "monitoramento.videoLayout";

type RowState = Record<string, "idle" | "loading" | "done" | "error">;

type Props = {
  initialChannels: MonitoredChannel[];
  initialVideos: MonitoredVideo[];
};

function formatInt(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("pt-BR");
}

function formatDelta(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n === 0) return "0";
  return n > 0 ? `+${formatInt(n)}` : formatInt(n);
}

function formatDateShort(s: string | null | undefined): string {
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

function StatusPill({ status }: { status: string }) {
  const cls =
    status === "active"
      ? "status-pill"
      : status === "paused"
      ? "status-pill warn"
      : "status-pill danger";
  return <span className={cls}>{status}</span>;
}

export function MonitoramentoView({
  initialChannels,
  initialVideos,
}: Props) {
  const [tab, setTab] = useState<Tab>("channels");
  const [channels, setChannels] = useState<MonitoredChannel[]>(initialChannels);
  const [videos, setVideos] = useState<MonitoredVideo[]>(initialVideos);
  const [bestByChannel, setBestByChannel] = useState<Record<number, MonitoredVideo[]>>({});
  const [rowState, setRowState] = useState<RowState>({});
  const [videoLayout, setVideoLayout] = useState<VideoLayout>("list");
  const [channelFilters, setChannelFilters] = useState<ChannelFilters>(
    DEFAULT_CHANNEL_FILTERS
  );
  const [videoFilters, setVideoFilters] = useState<VideoFilters>(
    DEFAULT_VIDEO_FILTERS
  );
  const toast = useToast();

  const filteredChannels = useMemo(
    () => applyChannelFilters(channels, channelFilters),
    [channels, channelFilters]
  );
  const filteredVideos = useMemo(
    () => applyVideoFilters(videos, videoFilters),
    [videos, videoFilters]
  );
  const availableChannelSources = useMemo(() => {
    const set = new Set<string>();
    for (const c of channels) {
      if (c.source) set.add(c.source);
    }
    return Array.from(set).sort();
  }, [channels]);

  // Carrega preferência de layout uma vez no mount (evita flicker no SSR).
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(VIDEO_LAYOUT_STORAGE_KEY);
      if (stored === "grid" || stored === "list") {
        setVideoLayout(stored);
      }
    } catch {
      /* localStorage indisponível, usa default */
    }
  }, []);

  function changeVideoLayout(next: VideoLayout) {
    setVideoLayout(next);
    try {
      window.localStorage.setItem(VIDEO_LAYOUT_STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }

  const markRow = (k: string, s: RowState[string]) =>
    setRowState((prev) => ({ ...prev, [k]: s }));

  const describeError = (e: unknown): string =>
    e instanceof Error ? e.message : String(e);

  // -------------------------------------------------------------------------
  // Canais
  // -------------------------------------------------------------------------
  async function refreshChannels() {
    try {
      const data = await apiGet<MonitoredChannel[]>("/api/monitoring/channels");
      setChannels(data);
    } catch (e) {
      toast.error(`Falha ao atualizar canais: ${describeError(e)}`);
    }
  }

  async function onSnapshotChannel(c: MonitoredChannel) {
    const k = `ch-snap:${c.id}`;
    markRow(k, "loading");
    try {
      await apiPost<ChannelSnapshot>(`/api/monitoring/channels/${c.id}/snapshot`, {});
      markRow(k, "done");
      await refreshChannels();
      if (bestByChannel[c.id] !== undefined) {
        await loadBestForChannel(c.id);
      }
      toast.success(`Snapshot atualizado: ${c.title}`);
    } catch (e) {
      markRow(k, "error");
      toast.error(`Snapshot falhou (${c.title}): ${describeError(e)}`);
    }
  }

  async function onToggleChannelStatus(c: MonitoredChannel) {
    const k = `ch-toggle:${c.id}`;
    markRow(k, "loading");
    const next = c.status === "active" ? "paused" : "active";
    try {
      await apiPatch<MonitoredChannel>(`/api/monitoring/channels/${c.id}`, { status: next });
      markRow(k, "idle");
      await refreshChannels();
      toast.success(`${c.title} ${next === "active" ? "retomado" : "pausado"}.`);
    } catch (e) {
      markRow(k, "error");
      toast.error(describeError(e));
    }
  }

  async function onDeleteChannel(c: MonitoredChannel) {
    if (!confirm(`Remover canal "${c.title}" e todo o histórico de snapshots?`)) return;
    const k = `ch-del:${c.id}`;
    markRow(k, "loading");
    try {
      await apiDelete(`/api/monitoring/channels/${c.id}`);
      setChannels((prev) => prev.filter((x) => x.id !== c.id));
      setVideos((prev) => prev.filter((v) => v.channel_id !== c.id));
      setBestByChannel((prev) => {
        const next = { ...prev };
        delete next[c.id];
        return next;
      });
      toast.success(`Canal "${c.title}" removido.`);
    } catch (e) {
      markRow(k, "error");
      toast.error(describeError(e));
    }
  }

  // -------------------------------------------------------------------------
  // Vídeos
  // -------------------------------------------------------------------------
  async function refreshVideos() {
    try {
      const data = await apiGet<MonitoredVideo[]>("/api/monitoring/videos");
      setVideos(data);
    } catch (e) {
      toast.error(`Falha ao atualizar vídeos: ${describeError(e)}`);
    }
  }

  async function onSnapshotVideo(v: MonitoredVideo) {
    const k = `vd-snap:${v.id}`;
    markRow(k, "loading");
    try {
      await apiPost<VideoSnapshot>(`/api/monitoring/videos/${v.id}/snapshot`, {});
      markRow(k, "done");
      await refreshVideos();
      toast.success("Snapshot do vídeo atualizado.");
    } catch (e) {
      markRow(k, "error");
      toast.error(describeError(e));
    }
  }

  async function onToggleVideoStatus(v: MonitoredVideo) {
    const k = `vd-toggle:${v.id}`;
    markRow(k, "loading");
    const next = v.status === "active" ? "paused" : "active";
    try {
      await apiPatch<MonitoredVideo>(`/api/monitoring/videos/${v.id}`, { status: next });
      markRow(k, "idle");
      await refreshVideos();
      toast.success(`Vídeo ${next === "active" ? "retomado" : "pausado"}.`);
    } catch (e) {
      markRow(k, "error");
      toast.error(describeError(e));
    }
  }

  async function onDeleteVideo(v: MonitoredVideo) {
    if (!confirm(`Remover o vídeo "${v.title.slice(0, 60)}" do monitoramento?`)) return;
    const k = `vd-del:${v.id}`;
    markRow(k, "loading");
    try {
      await apiDelete(`/api/monitoring/videos/${v.id}`);
      setVideos((prev) => prev.filter((x) => x.id !== v.id));
      toast.success("Vídeo removido.");
    } catch (e) {
      markRow(k, "error");
      toast.error(describeError(e));
    }
  }

  // -------------------------------------------------------------------------
  // Best videos por canal
  // -------------------------------------------------------------------------
  const loadBestForChannel = useCallback(
    async (channelId: number) => {
      try {
        const data = await apiGet<MonitoredVideo[]>(
          `/api/monitoring/channels/${channelId}/best-videos`
        );
        setBestByChannel((prev) => ({ ...prev, [channelId]: data }));
      } catch (e) {
        toast.error(e instanceof Error ? e.message : String(e));
      }
    },
    [toast]
  );

  async function onOpenBestTab() {
    setTab("best");
    // Carrega lazy para os canais ainda não buscados
    const pending = channels.filter((c) => bestByChannel[c.id] === undefined);
    await Promise.all(pending.map((c) => loadBestForChannel(c.id)));
  }

  const counts = useMemo(
    () => ({
      channels: channels.length,
      videos: videos.length,
    }),
    [channels.length, videos.length]
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="tabs">
        <button
          className={tab === "channels" ? "tab active" : "tab"}
          onClick={() => setTab("channels")}
        >
          Canais <span className="tab-count">{counts.channels}</span>
        </button>
        <button
          className={tab === "videos" ? "tab active" : "tab"}
          onClick={() => setTab("videos")}
        >
          Vídeos <span className="tab-count">{counts.videos}</span>
        </button>
        <button
          className={tab === "best" ? "tab active" : "tab"}
          onClick={onOpenBestTab}
        >
          Melhores vídeos
        </button>
      </div>

      {tab === "channels" && (
        <>
          <div style={{ marginBottom: -4 }}>
            <AddByLinkInput
              onChannelAdded={() => {
                refreshChannels();
              }}
              onVideoAdded={() => {
                // Backend criou o canal dono — atualizar canais e vídeos.
                refreshChannels();
                refreshVideos();
              }}
            />
          </div>
          <ChannelsFilterBar
            filters={channelFilters}
            onChange={setChannelFilters}
            totalCount={channels.length}
            filteredCount={filteredChannels.length}
            availableSources={availableChannelSources}
          />
          <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <SortableHeader<ChannelSortKey>
                  label="Canal"
                  columnKey="title"
                  currentSort={channelFilters.sort}
                  defaultSort={DEFAULT_CHANNEL_FILTERS.sort}
                  descKey="title_desc"
                  ascKey="title_asc"
                  onChange={(s) => setChannelFilters({ ...channelFilters, sort: s })}
                />
                <th>Status</th>
                <SortableHeader<ChannelSortKey>
                  label="Inscritos"
                  columnKey="subs"
                  currentSort={channelFilters.sort}
                  defaultSort={DEFAULT_CHANNEL_FILTERS.sort}
                  descKey="subs_desc"
                  ascKey="subs_asc"
                  onChange={(s) => setChannelFilters({ ...channelFilters, sort: s })}
                  style={{ textAlign: "right" }}
                />
                <SortableHeader<ChannelSortKey>
                  label="Δ Inscritos"
                  columnKey="delta_subs"
                  currentSort={channelFilters.sort}
                  defaultSort={DEFAULT_CHANNEL_FILTERS.sort}
                  descKey="delta_subs_desc"
                  onChange={(s) => setChannelFilters({ ...channelFilters, sort: s })}
                  style={{ textAlign: "right" }}
                />
                <SortableHeader<ChannelSortKey>
                  label="VPD recente"
                  columnKey="vpd"
                  currentSort={channelFilters.sort}
                  defaultSort={DEFAULT_CHANNEL_FILTERS.sort}
                  descKey="vpd_desc"
                  ascKey="vpd_asc"
                  onChange={(s) => setChannelFilters({ ...channelFilters, sort: s })}
                  style={{ textAlign: "right" }}
                />
                <SortableHeader<ChannelSortKey>
                  label="Último sync"
                  columnKey="last_sync"
                  currentSort={channelFilters.sort}
                  defaultSort={DEFAULT_CHANNEL_FILTERS.sort}
                  descKey="last_sync_desc"
                  onChange={(s) => setChannelFilters({ ...channelFilters, sort: s })}
                />
                <th style={{ width: 320 }}></th>
              </tr>
            </thead>
            <tbody>
              {filteredChannels.map((c) => {
                const snapState = rowState[`ch-snap:${c.id}`] ?? "idle";
                const toggleState = rowState[`ch-toggle:${c.id}`] ?? "idle";
                const delState = rowState[`ch-del:${c.id}`] ?? "idle";
                return (
                  <tr key={c.id}>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <ChannelAvatar url={c.thumbnail_url} title={c.title} size={36} />
                        <div style={{ minWidth: 0 }}>
                          <a href={c.url ?? "#"} target="_blank" rel="noreferrer">
                            {c.title}
                          </a>
                          {c.custom_url && (
                            <div className="muted" style={{ fontSize: 10 }}>{c.custom_url}</div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td><StatusPill status={c.status} /></td>
                    <td style={{ textAlign: "right" }}>{formatInt(c.subscribers)}</td>
                    <td style={{ textAlign: "right" }}>{formatDelta(c.delta_subscribers)}</td>
                    <td style={{ textAlign: "right" }}>
                      {c.avg_vpd_recent != null ? formatInt(Math.round(c.avg_vpd_recent)) : "—"}
                    </td>
                    <td className="muted" style={{ fontSize: 11 }}>
                      {formatDateShort(c.last_snapshot_at)}
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          className="btn-primary"
                          disabled={snapState === "loading"}
                          onClick={() => onSnapshotChannel(c)}
                        >
                          {snapState === "loading" ? "..." : "Atualizar agora"}
                        </button>
                        <button
                          className="btn-ghost"
                          disabled={toggleState === "loading"}
                          onClick={() => onToggleChannelStatus(c)}
                        >
                          {c.status === "active" ? "Pausar" : "Retomar"}
                        </button>
                        <button
                          className="btn-ghost danger"
                          disabled={delState === "loading"}
                          onClick={() => onDeleteChannel(c)}
                        >
                          Remover
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {filteredChannels.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted" style={{ textAlign: "center", padding: 16 }}>
                    {channels.length === 0 ? (
                      <>
                        nenhum canal monitorado. Cole um link/ID acima ou use a página{" "}
                        <a href="/descoberta">Descoberta</a>.
                      </>
                    ) : (
                      <>nenhum canal corresponde aos filtros aplicados.</>
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        </>
      )}

      {tab === "videos" && (
        <>
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: 4,
              marginBottom: -8,
            }}
          >
            <button
              type="button"
              className={
                videoLayout === "list" ? "btn-primary" : "btn-ghost"
              }
              onClick={() => changeVideoLayout("list")}
              aria-pressed={videoLayout === "list"}
              title="Visualização em lista"
            >
              Lista
            </button>
            <button
              type="button"
              className={
                videoLayout === "grid" ? "btn-primary" : "btn-ghost"
              }
              onClick={() => changeVideoLayout("grid")}
              aria-pressed={videoLayout === "grid"}
              title="Visualização em grade"
            >
              Grade
            </button>
          </div>

          <VideosFilterBar
            filters={videoFilters}
            onChange={setVideoFilters}
            totalCount={videos.length}
            filteredCount={filteredVideos.length}
            showSortDropdown={videoLayout === "grid"}
          />

          {filteredVideos.length === 0 ? (
            <div className="card">
              <p className="muted" style={{ margin: 0 }}>
                {videos.length === 0
                  ? "nenhum vídeo monitorado."
                  : "nenhum vídeo corresponde aos filtros aplicados."}
              </p>
            </div>
          ) : videoLayout === "list" ? (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <SortableHeader<VideoSortKey>
                      label="Vídeo"
                      columnKey="title"
                      currentSort={videoFilters.sort}
                      defaultSort={DEFAULT_VIDEO_FILTERS.sort}
                      descKey="title_desc"
                      ascKey="title_asc"
                      onChange={(s) => setVideoFilters({ ...videoFilters, sort: s })}
                    />
                    <th>Status</th>
                    <th>Origem</th>
                    <SortableHeader<VideoSortKey>
                      label="Views"
                      columnKey="views"
                      currentSort={videoFilters.sort}
                      defaultSort={DEFAULT_VIDEO_FILTERS.sort}
                      descKey="views_desc"
                      ascKey="views_asc"
                      onChange={(s) => setVideoFilters({ ...videoFilters, sort: s })}
                      style={{ textAlign: "right" }}
                    />
                    <SortableHeader<VideoSortKey>
                      label="VPD atual"
                      columnKey="vpd"
                      currentSort={videoFilters.sort}
                      defaultSort={DEFAULT_VIDEO_FILTERS.sort}
                      descKey="vpd_desc"
                      ascKey="vpd_asc"
                      onChange={(s) => setVideoFilters({ ...videoFilters, sort: s })}
                      style={{ textAlign: "right" }}
                    />
                    <SortableHeader<VideoSortKey>
                      label="VPD inicial"
                      columnKey="first_vpd"
                      currentSort={videoFilters.sort}
                      defaultSort={DEFAULT_VIDEO_FILTERS.sort}
                      descKey="first_vpd_desc"
                      onChange={(s) => setVideoFilters({ ...videoFilters, sort: s })}
                      style={{ textAlign: "right" }}
                    />
                    <SortableHeader<VideoSortKey>
                      label="Último sync"
                      columnKey="last_sync"
                      currentSort={videoFilters.sort}
                      defaultSort={DEFAULT_VIDEO_FILTERS.sort}
                      descKey="last_sync_desc"
                      onChange={(s) => setVideoFilters({ ...videoFilters, sort: s })}
                    />
                    <th style={{ width: 320 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredVideos.map((v) => {
                    const snapState = rowState[`vd-snap:${v.id}`] ?? "idle";
                    const toggleState = rowState[`vd-toggle:${v.id}`] ?? "idle";
                    const delState = rowState[`vd-del:${v.id}`] ?? "idle";
                    return (
                      <tr key={v.id}>
                        <td>
                          <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                            <VideoThumbnail url={v.thumbnail_url} title={v.title} width={200} />
                            <a
                              href={v.url ?? "#"}
                              target="_blank"
                              rel="noreferrer"
                              style={{ display: "block", paddingTop: 2 }}
                            >
                              {v.title}
                            </a>
                          </div>
                        </td>
                        <td><StatusPill status={v.status} /></td>
                        <td className="muted" style={{ fontSize: 11 }}>{v.tracking_source ?? "—"}</td>
                        <td style={{ textAlign: "right" }}>{formatInt(v.last_seen_views)}</td>
                        <td style={{ textAlign: "right" }}>
                          {v.last_seen_vpd != null ? formatInt(Math.round(v.last_seen_vpd)) : "—"}
                        </td>
                        <td style={{ textAlign: "right" }}>
                          {v.first_tracked_vpd != null ? formatInt(Math.round(v.first_tracked_vpd)) : "—"}
                        </td>
                        <td className="muted" style={{ fontSize: 11 }}>
                          {formatDateShort(v.last_seen_at)}
                        </td>
                        <td>
                          <div className="row-actions">
                            <button
                              className="btn-primary"
                              disabled={snapState === "loading"}
                              onClick={() => onSnapshotVideo(v)}
                            >
                              {snapState === "loading" ? "..." : "Atualizar agora"}
                            </button>
                            <button
                              className="btn-ghost"
                              disabled={toggleState === "loading"}
                              onClick={() => onToggleVideoStatus(v)}
                            >
                              {v.status === "active" ? "Pausar" : "Retomar"}
                            </button>
                            <button
                              className="btn-ghost danger"
                              disabled={delState === "loading"}
                              onClick={() => onDeleteVideo(v)}
                            >
                              Remover
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="video-grid">
              {filteredVideos.map((v) => {
                const snapState = rowState[`vd-snap:${v.id}`] ?? "idle";
                const toggleState = rowState[`vd-toggle:${v.id}`] ?? "idle";
                return (
                  <article key={v.id} className="video-card">
                    <a
                      href={v.url ?? "#"}
                      target="_blank"
                      rel="noreferrer"
                      className="video-card-thumb-link"
                    >
                      <VideoThumbnail
                        url={v.thumbnail_url}
                        title={v.title}
                        width={320}
                      />
                    </a>
                    <div className="video-card-body">
                      <a
                        href={v.url ?? "#"}
                        target="_blank"
                        rel="noreferrer"
                        className="video-card-title"
                        title={v.title}
                      >
                        {v.title}
                      </a>
                      <div className="video-card-meta">
                        <StatusPill status={v.status} />
                        <span className="muted" style={{ fontSize: 11 }}>
                          {formatInt(v.last_seen_views)} views
                        </span>
                        <span className="muted" style={{ fontSize: 11 }}>
                          VPD{" "}
                          {v.last_seen_vpd != null
                            ? formatInt(Math.round(v.last_seen_vpd))
                            : "—"}
                          {v.first_tracked_vpd != null && (
                            <>
                              {" "}
                              <span style={{ opacity: 0.7 }}>
                                (inicial{" "}
                                {formatInt(Math.round(v.first_tracked_vpd))})
                              </span>
                            </>
                          )}
                        </span>
                      </div>
                      <div className="row-actions" style={{ marginTop: 8 }}>
                        <button
                          className="btn-primary"
                          disabled={snapState === "loading"}
                          onClick={() => onSnapshotVideo(v)}
                        >
                          {snapState === "loading" ? "..." : "Atualizar"}
                        </button>
                        <button
                          className="btn-ghost"
                          disabled={toggleState === "loading"}
                          onClick={() => onToggleVideoStatus(v)}
                        >
                          {v.status === "active" ? "Pausar" : "Retomar"}
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </>
      )}

      {tab === "best" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {channels.length === 0 && (
            <div className="card">
              <div className="muted">
                adicione canais em <a href="/descoberta">Descoberta</a> primeiro.
              </div>
            </div>
          )}
          {channels.map((c) => {
            const list = bestByChannel[c.id];
            return (
              <section key={c.id} className="card">
                <header style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 10 }}>
                  <ChannelAvatar url={c.thumbnail_url} title={c.title} size={32} />
                  <h3 style={{ margin: 0, fontSize: 14 }}>
                    <a href={c.url ?? "#"} target="_blank" rel="noreferrer">{c.title}</a>
                  </h3>
                  <StatusPill status={c.status} />
                  <span className="muted" style={{ fontSize: 11 }}>
                    {list ? `${list.length} melhores detectados` : "carregando..."}
                  </span>
                </header>

                {list && list.length > 0 && (
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Vídeo</th>
                          <th style={{ textAlign: "right" }}>VPD atual</th>
                          <th style={{ textAlign: "right" }}>Views</th>
                          <th>Detectado em</th>
                        </tr>
                      </thead>
                      <tbody>
                        {list.map((v) => (
                          <tr key={v.id}>
                            <td>
                              <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                                <VideoThumbnail
                                  url={v.thumbnail_url}
                                  title={v.title}
                                  width={200}
                                />
                                <a
                                  href={v.url ?? "#"}
                                  target="_blank"
                                  rel="noreferrer"
                                  style={{ display: "block", paddingTop: 2 }}
                                >
                                  {v.title}
                                </a>
                              </div>
                            </td>
                            <td style={{ textAlign: "right" }}>
                              {v.last_seen_vpd != null ? formatInt(Math.round(v.last_seen_vpd)) : "—"}
                            </td>
                            <td style={{ textAlign: "right" }}>{formatInt(v.last_seen_views)}</td>
                            <td className="muted" style={{ fontSize: 11 }}>
                              {formatDateShort(v.first_tracked_at)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {list && list.length === 0 && (
                  <div className="muted" style={{ fontSize: 12 }}>
                    ainda não há melhores vídeos detectados. Clique em{" "}
                    <strong>Atualizar agora</strong> na aba Canais para gerar um snapshot.
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
