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
  type BulkOperationResponse,
  type ChannelSnapshot,
  type DeadChannelSuggestion,
  type MonitorSuggestion,
  type MonitoredChannel,
  type MonitoredVideo,
  type VideoSnapshot,
} from "@/lib/api";
import { useIsMobile } from "@/lib/useIsMobile";

type Tab = "channels" | "videos" | "best" | "suggestions";
type VideoLayout = "list" | "grid";

type BulkProgress = {
  label: string;
  total: number;
  done: number;
  success: number;
  failed: number;
};

const BULK_CONCURRENCY = 4;

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
  const [monitorSuggestions, setMonitorSuggestions] = useState<MonitorSuggestion[] | null>(null);
  const [deadSuggestions, setDeadSuggestions] = useState<DeadChannelSuggestion[] | null>(null);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [rowState, setRowState] = useState<RowState>({});
  const [videoLayout, setVideoLayout] = useState<VideoLayout>("list");
  const [channelFilters, setChannelFilters] = useState<ChannelFilters>(
    DEFAULT_CHANNEL_FILTERS
  );
  const [videoFilters, setVideoFilters] = useState<VideoFilters>(
    DEFAULT_VIDEO_FILTERS
  );
  const [selectedChannelIds, setSelectedChannelIds] = useState<Set<number>>(
    () => new Set()
  );
  const [selectedVideoIds, setSelectedVideoIds] = useState<Set<number>>(
    () => new Set()
  );
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkProgress, setBulkProgress] = useState<BulkProgress | null>(null);
  const isMobile = useIsMobile();
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

  // Suporte a deep-link `?tab=suggestions` (usado pela notificacao
  // "Sugestoes mudaram" da central). Aplica a aba uma vez no mount.
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const requested = params.get("tab");
      if (
        requested === "channels" ||
        requested === "videos" ||
        requested === "best" ||
        requested === "suggestions"
      ) {
        setTab(requested);
      }
    } catch {
      /* ignore */
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
  // Seleção múltipla — helpers genéricos
  // -------------------------------------------------------------------------
  const toggleChannelSelected = useCallback((id: number) => {
    setSelectedChannelIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleVideoSelected = useCallback((id: number) => {
    setSelectedVideoIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const setChannelsSelectAll = useCallback(
    (ids: number[], checked: boolean) => {
      setSelectedChannelIds((prev) => {
        const next = new Set(prev);
        if (checked) ids.forEach((i) => next.add(i));
        else ids.forEach((i) => next.delete(i));
        return next;
      });
    },
    []
  );

  const setVideosSelectAll = useCallback(
    (ids: number[], checked: boolean) => {
      setSelectedVideoIds((prev) => {
        const next = new Set(prev);
        if (checked) ids.forEach((i) => next.add(i));
        else ids.forEach((i) => next.delete(i));
        return next;
      });
    },
    []
  );

  const clearChannelSelection = useCallback(
    () => setSelectedChannelIds(new Set()),
    []
  );
  const clearVideoSelection = useCallback(
    () => setSelectedVideoIds(new Set()),
    []
  );

  // Após refresh, limpa IDs selecionados que não existem mais (stale).
  useEffect(() => {
    setSelectedChannelIds((prev) => {
      if (prev.size === 0) return prev;
      const present = new Set(channels.map((c) => c.id));
      let changed = false;
      const next = new Set<number>();
      for (const id of prev) {
        if (present.has(id)) next.add(id);
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [channels]);

  useEffect(() => {
    setSelectedVideoIds((prev) => {
      if (prev.size === 0) return prev;
      const present = new Set(videos.map((v) => v.id));
      let changed = false;
      const next = new Set<number>();
      for (const id of prev) {
        if (present.has(id)) next.add(id);
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [videos]);

  // -------------------------------------------------------------------------
  // Bulk handlers — canais
  // -------------------------------------------------------------------------
  function summarizeBulk(label: string, resp: BulkOperationResponse) {
    const { total, success_count, error_count, errors } = resp;
    if (error_count === 0) {
      toast.success(`${label}: ${success_count}/${total} concluídos.`);
      return;
    }
    const sample = errors
      .slice(0, 3)
      .map((e) => `#${e.id}: ${e.message}`)
      .join(" · ");
    const more = error_count > 3 ? ` (+${error_count - 3})` : "";
    if (success_count === 0) {
      toast.error(`${label}: ${total} falhas. ${sample}${more}`);
    } else {
      toast.error(
        `${label}: ${success_count}/${total} ok, ${error_count} falharam. ${sample}${more}`
      );
    }
  }

  async function runBulkChannels(
    label: string,
    method: "POST" | "PATCH",
    path: string,
    body: Record<string, unknown>
  ) {
    setBulkBusy(true);
    try {
      const resp =
        method === "POST"
          ? await apiPost<BulkOperationResponse>(path, body)
          : await apiPatch<BulkOperationResponse>(path, body);
      summarizeBulk(label, resp);
      // Mantém só os IDs que falharam — processados saem da seleção.
      const processed = new Set(resp.processed_ids);
      setSelectedChannelIds((prev) => {
        const next = new Set<number>();
        for (const id of prev) if (!processed.has(id)) next.add(id);
        return next;
      });
      await refreshChannels();
    } catch (e) {
      toast.error(`${label}: ${describeError(e)}`);
    } finally {
      setBulkBusy(false);
    }
  }

  // Snapshot em massa é o caso lento (≥3 units/canal, latência YouTube). Em
  // vez de bloquear no endpoint bulk, dispara N requests unitarios com
  // concorrencia limitada e atualiza progresso item-a-item.
  async function runItemizedSnapshot(opts: {
    label: string;
    ids: number[];
    snapshotPath: (id: number) => string;
    onSuccess: (id: number) => void;
    onRefresh: () => Promise<void>;
  }) {
    const { label, ids, snapshotPath, onSuccess, onRefresh } = opts;
    const total = ids.length;
    if (total === 0) return;

    setBulkBusy(true);
    setBulkProgress({ label, total, done: 0, success: 0, failed: 0 });

    const errors: Array<{ id: number; message: string }> = [];

    // Pool com concorrencia BULK_CONCURRENCY: workers consomem da fila.
    const queue = [...ids];
    async function worker() {
      while (queue.length > 0) {
        const id = queue.shift();
        if (id === undefined) return;
        try {
          await apiPost(snapshotPath(id), {});
          onSuccess(id);
          setBulkProgress((p) =>
            p ? { ...p, done: p.done + 1, success: p.success + 1 } : p
          );
        } catch (e) {
          errors.push({ id, message: e instanceof Error ? e.message : String(e) });
          setBulkProgress((p) =>
            p ? { ...p, done: p.done + 1, failed: p.failed + 1 } : p
          );
        }
      }
    }

    const workers = Array.from(
      { length: Math.min(BULK_CONCURRENCY, total) },
      () => worker()
    );
    await Promise.all(workers);

    summarizeBulk(label, {
      total,
      success_count: total - errors.length,
      error_count: errors.length,
      processed_ids: [],
      errors,
    });

    await onRefresh();
    setBulkBusy(false);
    // Mantém a barra na tela por 2s pra usuario ler o resultado final.
    setTimeout(() => setBulkProgress(null), 2000);
  }

  function onBulkSnapshotChannels() {
    const ids = Array.from(selectedChannelIds);
    if (ids.length === 0) return;
    runItemizedSnapshot({
      label: "Atualizar canais",
      ids,
      snapshotPath: (id) => `/api/monitoring/channels/${id}/snapshot`,
      onSuccess: (id) =>
        setSelectedChannelIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        }),
      onRefresh: refreshChannels,
    });
  }

  function onBulkSetChannelStatus(targetStatus: "active" | "paused") {
    const ids = Array.from(selectedChannelIds);
    if (ids.length === 0) return;
    const label = targetStatus === "active" ? "Retomar canais" : "Pausar canais";
    runBulkChannels(
      label,
      "PATCH",
      "/api/monitoring/channels/bulk-status",
      { ids, status: targetStatus }
    );
  }

  function onBulkDeleteChannels() {
    const ids = Array.from(selectedChannelIds);
    if (ids.length === 0) return;
    if (
      !confirm(
        `Remover ${ids.length} canal(is) e todo o histórico de snapshots? Esta ação não pode ser desfeita.`
      )
    ) {
      return;
    }
    runBulkChannels(
      "Remover canais",
      "POST",
      "/api/monitoring/channels/bulk-delete",
      { ids }
    );
  }

  // -------------------------------------------------------------------------
  // Bulk handlers — vídeos
  // -------------------------------------------------------------------------
  async function runBulkVideos(
    label: string,
    method: "POST" | "PATCH",
    path: string,
    body: Record<string, unknown>
  ) {
    setBulkBusy(true);
    try {
      const resp =
        method === "POST"
          ? await apiPost<BulkOperationResponse>(path, body)
          : await apiPatch<BulkOperationResponse>(path, body);
      summarizeBulk(label, resp);
      const processed = new Set(resp.processed_ids);
      setSelectedVideoIds((prev) => {
        const next = new Set<number>();
        for (const id of prev) if (!processed.has(id)) next.add(id);
        return next;
      });
      await refreshVideos();
    } catch (e) {
      toast.error(`${label}: ${describeError(e)}`);
    } finally {
      setBulkBusy(false);
    }
  }

  function onBulkSnapshotVideos() {
    const ids = Array.from(selectedVideoIds);
    if (ids.length === 0) return;
    runItemizedSnapshot({
      label: "Atualizar vídeos",
      ids,
      snapshotPath: (id) => `/api/monitoring/videos/${id}/snapshot`,
      onSuccess: (id) =>
        setSelectedVideoIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        }),
      onRefresh: refreshVideos,
    });
  }

  function onBulkSetVideoStatus(targetStatus: "active" | "paused") {
    const ids = Array.from(selectedVideoIds);
    if (ids.length === 0) return;
    const label = targetStatus === "active" ? "Retomar vídeos" : "Pausar vídeos";
    runBulkVideos(
      label,
      "PATCH",
      "/api/monitoring/videos/bulk-status",
      { ids, status: targetStatus }
    );
  }

  function onBulkDeleteVideos() {
    const ids = Array.from(selectedVideoIds);
    if (ids.length === 0) return;
    if (!confirm(`Remover ${ids.length} vídeo(s) do monitoramento?`)) return;
    runBulkVideos(
      "Remover vídeos",
      "POST",
      "/api/monitoring/videos/bulk-delete",
      { ids }
    );
  }

  // -------------------------------------------------------------------------
  // Sugestões (recomendações de monitorar / remover por canal morto)
  // -------------------------------------------------------------------------
  const loadSuggestions = useCallback(async () => {
    setLoadingSuggestions(true);
    try {
      const [toMon, toRemove] = await Promise.all([
        apiGet<MonitorSuggestion[]>("/api/suggestions/to-monitor"),
        apiGet<DeadChannelSuggestion[]>("/api/suggestions/to-remove"),
      ]);
      setMonitorSuggestions(toMon);
      setDeadSuggestions(toRemove);
    } catch (e) {
      toast.error(`Falha ao carregar sugestões: ${describeError(e)}`);
    } finally {
      setLoadingSuggestions(false);
    }
  }, [toast]);

  async function onOpenSuggestionsTab() {
    setTab("suggestions");
    if (monitorSuggestions === null && deadSuggestions === null) {
      await loadSuggestions();
    }
  }

  // Carrega sugestoes se a aba foi ativada por deep-link (sem passar pelo
  // handler do botao). Sem este efeito, abrir `/monitoramento?tab=suggestions`
  // mostraria a aba vazia ate o usuario clicar em "Recarregar".
  useEffect(() => {
    if (tab !== "suggestions") return;
    if (monitorSuggestions !== null || deadSuggestions !== null) return;
    if (loadingSuggestions) return;
    void loadSuggestions();
  }, [tab, monitorSuggestions, deadSuggestions, loadingSuggestions, loadSuggestions]);

  async function onAddSuggestedChannel(s: MonitorSuggestion) {
    try {
      await apiPost<MonitoredChannel>("/api/monitoring/channels", {
        youtube_channel_id: s.youtube_channel_id,
      });
      toast.success(`Monitorando "${s.title}".`);
      // Tira da lista de sugestões na hora pra dar feedback imediato.
      setMonitorSuggestions((prev) =>
        prev ? prev.filter((x) => x.youtube_channel_id !== s.youtube_channel_id) : prev
      );
      await refreshChannels();
    } catch (e) {
      toast.error(describeError(e));
    }
  }

  async function onPauseDeadChannel(s: DeadChannelSuggestion) {
    try {
      await apiPatch<MonitoredChannel>(`/api/monitoring/channels/${s.channel_id}`, {
        status: "paused",
      });
      toast.success(`"${s.title}" pausado.`);
      setDeadSuggestions((prev) =>
        prev ? prev.filter((x) => x.channel_id !== s.channel_id) : prev
      );
      await refreshChannels();
    } catch (e) {
      toast.error(describeError(e));
    }
  }

  async function onRemoveDeadChannel(s: DeadChannelSuggestion) {
    if (
      !confirm(
        `Remover "${s.title}" e todo o histórico de snapshots? O canal entrará na blacklist.`
      )
    ) {
      return;
    }
    try {
      await apiDelete(`/api/monitoring/channels/${s.channel_id}`);
      toast.success(`"${s.title}" removido.`);
      setDeadSuggestions((prev) =>
        prev ? prev.filter((x) => x.channel_id !== s.channel_id) : prev
      );
      setChannels((prev) => prev.filter((c) => c.id !== s.channel_id));
    } catch (e) {
      toast.error(describeError(e));
    }
  }

  // -------------------------------------------------------------------------
  // Best videos por canal
  // -------------------------------------------------------------------------
  // Endpoint singular ainda usado quando atualizamos um canal específico
  // após snapshot manual.
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

  // Endpoint batch: carrega os "melhores" de varios canais em UMA request.
  // Usado pela paginacao da aba Best.
  const loadBestForChannelsBatch = useCallback(
    async (channelIds: number[]) => {
      if (channelIds.length === 0) return;
      try {
        const idsParam = channelIds.join(",");
        const data = await apiGet<Record<string, MonitoredVideo[]>>(
          `/api/monitoring/channels/best-videos?ids=${idsParam}`
        );
        setBestByChannel((prev) => {
          const next = { ...prev };
          for (const id of channelIds) {
            // Backend devolve chave string (JSON object). Mantemos `[]` como
            // marcador de "ja consultado, sem melhores ainda".
            next[id] = data[String(id)] ?? [];
          }
          return next;
        });
      } catch (e) {
        toast.error(e instanceof Error ? e.message : String(e));
      }
    },
    [toast]
  );

  // Paginacao da aba Best: 50 canais por pagina, navegacao por
  // [anterior][proxima]. Cada troca de pagina dispara 1 unica request batch.
  const BEST_PAGE_SIZE = 50;
  const [bestPage, setBestPage] = useState(0);
  const bestTotalPages = Math.max(
    1,
    Math.ceil(channels.length / BEST_PAGE_SIZE)
  );
  const bestPageChannels = useMemo(() => {
    const start = bestPage * BEST_PAGE_SIZE;
    return channels.slice(start, start + BEST_PAGE_SIZE);
  }, [channels, bestPage]);

  // Reseta a pagina quando muda o conjunto de canais (ex: deletar canal numa
  // pagina vazia o ultimo item).
  useEffect(() => {
    if (bestPage > 0 && bestPage >= bestTotalPages) {
      setBestPage(Math.max(0, bestTotalPages - 1));
    }
  }, [bestPage, bestTotalPages]);

  // Carrega a pagina visivel da aba Best (so o que ainda nao tem cache).
  useEffect(() => {
    if (tab !== "best") return;
    const pending = bestPageChannels
      .filter((c) => bestByChannel[c.id] === undefined)
      .map((c) => c.id);
    if (pending.length === 0) return;
    void loadBestForChannelsBatch(pending);
  }, [tab, bestPageChannels, bestByChannel, loadBestForChannelsBatch]);

  function onOpenBestTab() {
    setTab("best");
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
        <button
          className={tab === "suggestions" ? "tab active" : "tab"}
          onClick={onOpenSuggestionsTab}
        >
          Sugestões
          {monitorSuggestions != null && deadSuggestions != null && (
            <span className="tab-count">
              {monitorSuggestions.length + deadSuggestions.length}
            </span>
          )}
        </button>
      </div>

      {bulkProgress && <BulkProgressBar progress={bulkProgress} />}

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
            showSortDropdown={isMobile}
          />
          {(() => {
            const visibleIds = filteredChannels.map((c) => c.id);
            const visibleSelectedCount = visibleIds.filter((id) =>
              selectedChannelIds.has(id)
            ).length;
            const allVisibleSelected =
              visibleIds.length > 0 &&
              visibleSelectedCount === visibleIds.length;
            const selectedChannels = filteredChannels.filter((c) =>
              selectedChannelIds.has(c.id)
            );
            const allActive =
              selectedChannels.length > 0 &&
              selectedChannels.every((c) => c.status === "active");
            const allPaused =
              selectedChannels.length > 0 &&
              selectedChannels.every((c) => c.status === "paused");
            return (
              selectedChannelIds.size > 0 && (
                <div className="bulk-actions-bar">
                  <div className="bulk-actions-info">
                    <strong>{selectedChannelIds.size}</strong> canal(is)
                    selecionado(s)
                  </div>
                  <div className="bulk-actions-buttons">
                    <button
                      className="btn-primary"
                      disabled={bulkBusy}
                      onClick={onBulkSnapshotChannels}
                    >
                      Atualizar agora
                    </button>
                    {allActive ? (
                      <button
                        className="btn-ghost"
                        disabled={bulkBusy}
                        onClick={() => onBulkSetChannelStatus("paused")}
                      >
                        Pausar
                      </button>
                    ) : allPaused ? (
                      <button
                        className="btn-ghost"
                        disabled={bulkBusy}
                        onClick={() => onBulkSetChannelStatus("active")}
                      >
                        Retomar
                      </button>
                    ) : (
                      <>
                        <button
                          className="btn-ghost"
                          disabled={bulkBusy}
                          onClick={() => onBulkSetChannelStatus("paused")}
                        >
                          Pausar selecionados
                        </button>
                        <button
                          className="btn-ghost"
                          disabled={bulkBusy}
                          onClick={() => onBulkSetChannelStatus("active")}
                        >
                          Retomar selecionados
                        </button>
                      </>
                    )}
                    <button
                      className="btn-ghost danger"
                      disabled={bulkBusy}
                      onClick={onBulkDeleteChannels}
                    >
                      Remover
                    </button>
                    <button
                      className="btn-ghost"
                      disabled={bulkBusy}
                      onClick={clearChannelSelection}
                    >
                      Limpar seleção
                    </button>
                  </div>
                </div>
              )
            );
          })()}
          <div className="table-wrap desktop-only">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: 36 }}>
                  <input
                    type="checkbox"
                    aria-label="selecionar todos os canais visíveis"
                    checked={
                      filteredChannels.length > 0 &&
                      filteredChannels.every((c) =>
                        selectedChannelIds.has(c.id)
                      )
                    }
                    ref={(el) => {
                      if (!el) return;
                      const visible = filteredChannels.length;
                      const sel = filteredChannels.filter((c) =>
                        selectedChannelIds.has(c.id)
                      ).length;
                      el.indeterminate = sel > 0 && sel < visible;
                    }}
                    onChange={(e) =>
                      setChannelsSelectAll(
                        filteredChannels.map((c) => c.id),
                        e.target.checked
                      )
                    }
                    disabled={filteredChannels.length === 0}
                  />
                </th>
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
                const isSelected = selectedChannelIds.has(c.id);
                return (
                  <tr key={c.id} className={isSelected ? "row-selected" : ""}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`selecionar canal ${c.title}`}
                        checked={isSelected}
                        onChange={() => toggleChannelSelected(c.id)}
                      />
                    </td>
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
                          {c.status === "removed" && c.notes && (
                            <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                              {c.notes}
                            </div>
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
                  <td colSpan={8} className="muted" style={{ textAlign: "center", padding: 16 }}>
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

        {/* Versão mobile: cards stackados (≤768px) */}
        <div className="mobile-only">
          {filteredChannels.length === 0 ? (
            <div className="card">
              <p className="muted" style={{ margin: 0 }}>
                {channels.length === 0 ? (
                  <>
                    nenhum canal monitorado. Cole um link/ID acima ou use a página{" "}
                    <a href="/descoberta">Descoberta</a>.
                  </>
                ) : (
                  <>nenhum canal corresponde aos filtros aplicados.</>
                )}
              </p>
            </div>
          ) : (
            <>
              <div className="mobile-list-toolbar">
                {(() => {
                  const allSelected =
                    filteredChannels.length > 0 &&
                    filteredChannels.every((c) =>
                      selectedChannelIds.has(c.id)
                    );
                  return (
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() =>
                        setChannelsSelectAll(
                          filteredChannels.map((c) => c.id),
                          !allSelected
                        )
                      }
                    >
                      {allSelected ? "Desmarcar todos" : "Selecionar todos"}
                    </button>
                  );
                })()}
                <span className="spacer" />
                <span>{filteredChannels.length} canal(is)</span>
              </div>
              <div className="mobile-card-list">
                {filteredChannels.map((c) => {
                  const snapState = rowState[`ch-snap:${c.id}`] ?? "idle";
                  const toggleState = rowState[`ch-toggle:${c.id}`] ?? "idle";
                  const delState = rowState[`ch-del:${c.id}`] ?? "idle";
                  const isSelected = selectedChannelIds.has(c.id);
                  return (
                    <article
                      key={c.id}
                      className={
                        isSelected ? "mobile-card row-selected" : "mobile-card"
                      }
                    >
                      <div className="mobile-card-header">
                        <label className="mobile-card-checkbox">
                          <input
                            type="checkbox"
                            aria-label={`selecionar canal ${c.title}`}
                            checked={isSelected}
                            onChange={() => toggleChannelSelected(c.id)}
                          />
                        </label>
                        <ChannelAvatar
                          url={c.thumbnail_url}
                          title={c.title}
                          size={40}
                        />
                        <div className="mobile-card-title">
                          <a
                            href={c.url ?? "#"}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {c.title}
                          </a>
                          <StatusPill status={c.status} />
                        </div>
                      </div>

                      <div className="mobile-card-meta">
                        <div>
                          <span className="label">Inscritos</span>
                          <span className="value">
                            {formatInt(c.subscribers)}
                          </span>
                        </div>
                        <div>
                          <span className="label">Δ Inscritos</span>
                          <span className="value">
                            {formatDelta(c.delta_subscribers)}
                          </span>
                        </div>
                        <div>
                          <span className="label">VPD recente</span>
                          <span className="value">
                            {c.avg_vpd_recent != null
                              ? formatInt(Math.round(c.avg_vpd_recent))
                              : "—"}
                          </span>
                        </div>
                        <div>
                          <span className="label">Último sync</span>
                          <span className="value">
                            {formatDateShort(c.last_snapshot_at)}
                          </span>
                        </div>
                        {c.status === "removed" && c.notes && (
                          <div style={{ gridColumn: "1 / -1" }}>
                            <span className="label">Contexto</span>
                            <span className="value">{c.notes}</span>
                          </div>
                        )}
                      </div>

                      <div className="mobile-card-actions">
                        <button
                          className="btn-primary"
                          disabled={snapState === "loading"}
                          onClick={() => onSnapshotChannel(c)}
                        >
                          {snapState === "loading"
                            ? "..."
                            : "Atualizar agora"}
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
                    </article>
                  );
                })}
              </div>
            </>
          )}
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
            showSortDropdown={videoLayout === "grid" || isMobile}
          />

          {(() => {
            const selectedVideos = filteredVideos.filter((v) =>
              selectedVideoIds.has(v.id)
            );
            const allActive =
              selectedVideos.length > 0 &&
              selectedVideos.every((v) => v.status === "active");
            const allPaused =
              selectedVideos.length > 0 &&
              selectedVideos.every((v) => v.status === "paused");
            return (
              selectedVideoIds.size > 0 && (
                <div className="bulk-actions-bar">
                  <div className="bulk-actions-info">
                    <strong>{selectedVideoIds.size}</strong> vídeo(s)
                    selecionado(s)
                  </div>
                  <div className="bulk-actions-buttons">
                    <button
                      className="btn-primary"
                      disabled={bulkBusy}
                      onClick={onBulkSnapshotVideos}
                    >
                      Atualizar agora
                    </button>
                    {allActive ? (
                      <button
                        className="btn-ghost"
                        disabled={bulkBusy}
                        onClick={() => onBulkSetVideoStatus("paused")}
                      >
                        Pausar
                      </button>
                    ) : allPaused ? (
                      <button
                        className="btn-ghost"
                        disabled={bulkBusy}
                        onClick={() => onBulkSetVideoStatus("active")}
                      >
                        Retomar
                      </button>
                    ) : (
                      <>
                        <button
                          className="btn-ghost"
                          disabled={bulkBusy}
                          onClick={() => onBulkSetVideoStatus("paused")}
                        >
                          Pausar selecionados
                        </button>
                        <button
                          className="btn-ghost"
                          disabled={bulkBusy}
                          onClick={() => onBulkSetVideoStatus("active")}
                        >
                          Retomar selecionados
                        </button>
                      </>
                    )}
                    <button
                      className="btn-ghost danger"
                      disabled={bulkBusy}
                      onClick={onBulkDeleteVideos}
                    >
                      Remover
                    </button>
                    <button
                      className="btn-ghost"
                      disabled={bulkBusy}
                      onClick={clearVideoSelection}
                    >
                      Limpar seleção
                    </button>
                  </div>
                </div>
              )
            );
          })()}

          {filteredVideos.length === 0 ? (
            <div className="card">
              <p className="muted" style={{ margin: 0 }}>
                {videos.length === 0
                  ? "nenhum vídeo monitorado."
                  : "nenhum vídeo corresponde aos filtros aplicados."}
              </p>
            </div>
          ) : videoLayout === "list" ? (
            <>
            <div className="table-wrap desktop-only">
              <table className="table">
                <thead>
                  <tr>
                    <th style={{ width: 36 }}>
                      <input
                        type="checkbox"
                        aria-label="selecionar todos os vídeos visíveis"
                        checked={
                          filteredVideos.length > 0 &&
                          filteredVideos.every((v) =>
                            selectedVideoIds.has(v.id)
                          )
                        }
                        ref={(el) => {
                          if (!el) return;
                          const visible = filteredVideos.length;
                          const sel = filteredVideos.filter((v) =>
                            selectedVideoIds.has(v.id)
                          ).length;
                          el.indeterminate = sel > 0 && sel < visible;
                        }}
                        onChange={(e) =>
                          setVideosSelectAll(
                            filteredVideos.map((v) => v.id),
                            e.target.checked
                          )
                        }
                        disabled={filteredVideos.length === 0}
                      />
                    </th>
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
                    const isSelected = selectedVideoIds.has(v.id);
                    return (
                      <tr key={v.id} className={isSelected ? "row-selected" : ""}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`selecionar vídeo ${v.title}`}
                            checked={isSelected}
                            onChange={() => toggleVideoSelected(v.id)}
                          />
                        </td>
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
                            {v.channel_title && (
                              <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                                canal: 
                                {v.channel_url ? (
                                  <a href={v.channel_url} target="_blank" rel="noreferrer">
                                    {v.channel_title}
                                  </a>
                                ) : (
                                  v.channel_title
                                )}
                              </div>
                            )}
                            {v.unavailable_reason && (
                              <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                                indisponivel desde {formatDateShort(v.unavailable_since)} ({v.unavailable_reason})
                              </div>
                            )}
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

            {/* Versão mobile da aba Vídeos > list: cards stackados (≤768px) */}
            <div className="mobile-only">
              <div className="mobile-list-toolbar">
                {(() => {
                  const allSelected =
                    filteredVideos.length > 0 &&
                    filteredVideos.every((v) =>
                      selectedVideoIds.has(v.id)
                    );
                  return (
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() =>
                        setVideosSelectAll(
                          filteredVideos.map((v) => v.id),
                          !allSelected
                        )
                      }
                    >
                      {allSelected ? "Desmarcar todos" : "Selecionar todos"}
                    </button>
                  );
                })()}
                <span className="spacer" />
                <span>{filteredVideos.length} vídeo(s)</span>
              </div>
              <div className="mobile-card-list">
                {filteredVideos.map((v) => {
                  const snapState = rowState[`vd-snap:${v.id}`] ?? "idle";
                  const toggleState = rowState[`vd-toggle:${v.id}`] ?? "idle";
                  const delState = rowState[`vd-del:${v.id}`] ?? "idle";
                  const isSelected = selectedVideoIds.has(v.id);
                  return (
                    <article
                      key={v.id}
                      className={
                        isSelected
                          ? "mobile-card row-selected"
                          : "mobile-card"
                      }
                    >
                      <div className="mobile-card-header">
                        <label className="mobile-card-checkbox">
                          <input
                            type="checkbox"
                            aria-label={`selecionar vídeo ${v.title}`}
                            checked={isSelected}
                            onChange={() => toggleVideoSelected(v.id)}
                          />
                        </label>
                        <div className="mobile-card-title">
                          <a
                            href={v.url ?? "#"}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {v.title}
                          </a>
                          <StatusPill status={v.status} />
                          {v.channel_title && (
                            <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                              canal: 
                              {v.channel_url ? (
                                <a href={v.channel_url} target="_blank" rel="noreferrer">
                                  {v.channel_title}
                                </a>
                              ) : (
                                v.channel_title
                              )}
                            </div>
                          )}
                          {v.unavailable_reason && (
                            <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                              indisponivel desde {formatDateShort(v.unavailable_since)} ({v.unavailable_reason})
                            </div>
                          )}
                        </div>
                      </div>

                      <a
                        href={v.url ?? "#"}
                        target="_blank"
                        rel="noreferrer"
                        className="mobile-card-thumb"
                      >
                        <VideoThumbnail
                          url={v.thumbnail_url}
                          title={v.title}
                          width={400}
                        />
                      </a>

                      <div className="mobile-card-meta">
                        <div>
                          <span className="label">Views</span>
                          <span className="value">
                            {formatInt(v.last_seen_views)}
                          </span>
                        </div>
                        <div>
                          <span className="label">VPD atual</span>
                          <span className="value">
                            {v.last_seen_vpd != null
                              ? formatInt(Math.round(v.last_seen_vpd))
                              : "—"}
                          </span>
                        </div>
                        <div>
                          <span className="label">VPD inicial</span>
                          <span className="value">
                            {v.first_tracked_vpd != null
                              ? formatInt(Math.round(v.first_tracked_vpd))
                              : "—"}
                          </span>
                        </div>
                        <div>
                          <span className="label">Último sync</span>
                          <span className="value">
                            {formatDateShort(v.last_seen_at)}
                          </span>
                        </div>
                        {v.unavailable_reason && (
                          <div style={{ gridColumn: "1 / -1" }}>
                            <span className="label">Contexto</span>
                            <span className="value">
                              indisponivel desde {formatDateShort(v.unavailable_since)} ({v.unavailable_reason})
                            </span>
                          </div>
                        )}
                      </div>

                      <div className="mobile-card-actions">
                        <button
                          className="btn-primary"
                          disabled={snapState === "loading"}
                          onClick={() => onSnapshotVideo(v)}
                        >
                          {snapState === "loading"
                            ? "..."
                            : "Atualizar agora"}
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
                    </article>
                  );
                })}
              </div>
            </div>
            </>
          ) : (
            <div className="video-grid">
              {filteredVideos.map((v) => {
                const snapState = rowState[`vd-snap:${v.id}`] ?? "idle";
                const toggleState = rowState[`vd-toggle:${v.id}`] ?? "idle";
                const isSelected = selectedVideoIds.has(v.id);
                return (
                  <article
                    key={v.id}
                    className={
                      isSelected ? "video-card video-card-selected" : "video-card"
                    }
                  >
                    <label
                      className="video-card-select"
                      title={isSelected ? "desselecionar" : "selecionar"}
                    >
                      <input
                        type="checkbox"
                        aria-label={`selecionar vídeo ${v.title}`}
                        checked={isSelected}
                        onChange={() => toggleVideoSelected(v.id)}
                      />
                    </label>
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
                      {v.channel_title && (
                        <span className="muted" style={{ fontSize: 11 }}>
                          canal: 
                          {v.channel_url ? (
                            <a href={v.channel_url} target="_blank" rel="noreferrer">
                              {v.channel_title}
                            </a>
                          ) : (
                            v.channel_title
                          )}
                        </span>
                      )}
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
                        {v.unavailable_reason && (
                          <span className="muted" style={{ fontSize: 11 }}>
                            indisponivel desde {formatDateShort(v.unavailable_since)}
                          </span>
                        )}
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
          {channels.length > BEST_PAGE_SIZE && (
            <div
              className="card"
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 12px",
              }}
            >
              <span className="muted" style={{ fontSize: 12 }}>
                {channels.length.toLocaleString("pt-BR")} canais ·{" "}
                pagina {bestPage + 1} de {bestTotalPages} ·{" "}
                exibindo {bestPageChannels.length} (
                {bestPage * BEST_PAGE_SIZE + 1}–
                {bestPage * BEST_PAGE_SIZE + bestPageChannels.length})
              </span>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  className="btn-ghost"
                  disabled={bestPage === 0}
                  onClick={() => setBestPage((p) => Math.max(0, p - 1))}
                >
                  ← anterior
                </button>
                <button
                  type="button"
                  className="btn-ghost"
                  disabled={bestPage >= bestTotalPages - 1}
                  onClick={() =>
                    setBestPage((p) => Math.min(bestTotalPages - 1, p + 1))
                  }
                >
                  proxima →
                </button>
              </div>
            </div>
          )}
          {bestPageChannels.map((c) => {
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

      {tab === "suggestions" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card" style={{ background: "rgba(79, 140, 255, 0.05)" }}>
            <div style={{ fontSize: 13 }}>
              <strong>Recomendações automáticas.</strong>{" "}
              <span className="muted">
                As ações abaixo são <strong>sugestões</strong> baseadas nos
                thresholds configurados em{" "}
                <a href="/configuracoes">Configurações → Sugestões</a>. Nada é
                executado automaticamente — você decide o que aceitar.
              </span>
              <button
                type="button"
                className="btn-ghost"
                onClick={loadSuggestions}
                disabled={loadingSuggestions}
                style={{ marginLeft: 12 }}
              >
                {loadingSuggestions ? "..." : "Recarregar"}
              </button>
            </div>
          </div>

          <SuggestionsToMonitor
            items={monitorSuggestions}
            loading={loadingSuggestions}
            onAdd={onAddSuggestedChannel}
          />

          <SuggestionsToRemove
            items={deadSuggestions}
            loading={loadingSuggestions}
            onPause={onPauseDeadChannel}
            onRemove={onRemoveDeadChannel}
          />
        </div>
      )}
    </div>
  );
}

function SuggestionsToMonitor({
  items,
  loading,
  onAdd,
}: {
  items: MonitorSuggestion[] | null;
  loading: boolean;
  onAdd: (s: MonitorSuggestion) => void;
}) {
  return (
    <section className="card">
      <header style={{ marginBottom: 10 }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>
          Recomendados para monitorar{" "}
          <span className="muted" style={{ fontWeight: 400, fontSize: 11 }}>
            (canais novos com VPD alto ou Canal Viral, ainda fora do monitoramento)
          </span>
        </h3>
      </header>
      {loading && items === null ? (
        <div className="muted" style={{ fontSize: 12 }}>carregando…</div>
      ) : !items || items.length === 0 ? (
        <div className="muted" style={{ fontSize: 12 }}>
          nenhuma recomendação no momento — aguarde a descoberta automática
          encontrar canais novos.
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Canal</th>
                <th style={{ textAlign: "right" }}>Inscritos</th>
                <th style={{ textAlign: "right" }}>VPD recente</th>
                <th style={{ textAlign: "right" }}>Top vídeo</th>
                <th>Por que</th>
                <th style={{ width: 140 }}></th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.youtube_channel_id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <ChannelAvatar url={s.thumbnail_url} title={s.title} size={32} />
                      <div style={{ minWidth: 0 }}>
                        <a href={s.url ?? "#"} target="_blank" rel="noreferrer">
                          {s.title}
                        </a>
                        <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                          {s.suggestion_kind === "early_breakout"
                            ? "Canal Viral"
                            : s.suggestion_kind === "mixed"
                            ? "Canal Viral + VPD alto"
                            : "canal jovem com VPD alto"}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {s.subscribers != null ? s.subscribers.toLocaleString("pt-BR") : "—"}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {s.avg_vpd_recent != null
                        ? Math.round(s.avg_vpd_recent).toLocaleString("pt-BR")
                        : "—"}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {s.top_video_url ? (
                      <a href={s.top_video_url} target="_blank" rel="noreferrer">
                        {s.top_video_views != null
                          ? s.top_video_views.toLocaleString("pt-BR")
                          : "—"}
                      </a>
                    ) : (
                      (s.top_video_views != null
                        ? s.top_video_views.toLocaleString("pt-BR")
                        : "—")
                    )}
                    {s.top_video_title && (
                      <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                        {s.top_video_title}
                      </div>
                    )}
                  </td>
                  <td className="muted" style={{ fontSize: 11 }}>{s.reason}</td>
                  <td>
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={() => onAdd(s)}
                    >
                      Monitorar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function SuggestionsToRemove({
  items,
  loading,
  onPause,
  onRemove,
}: {
  items: DeadChannelSuggestion[] | null;
  loading: boolean;
  onPause: (s: DeadChannelSuggestion) => void;
  onRemove: (s: DeadChannelSuggestion) => void;
}) {
  return (
    <section className="card">
      <header style={{ marginBottom: 10 }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>
          Possivelmente mortos — sugeridos para pausar/remover{" "}
          <span className="muted" style={{ fontWeight: 400, fontSize: 11 }}>
            (sem uploads recentes, VPD baixo e sinal estagnado)
          </span>
        </h3>
      </header>
      {loading && items === null ? (
        <div className="muted" style={{ fontSize: 12 }}>carregando…</div>
      ) : !items || items.length === 0 ? (
        <div className="muted" style={{ fontSize: 12 }}>
          nenhum canal monitorado bate todos os critérios de "morto" no momento.
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Canal</th>
                <th style={{ textAlign: "right" }}>Dias sem upload</th>
                <th style={{ textAlign: "right" }}>VPD recente</th>
                <th>Sinal</th>
                <th>Por que</th>
                <th style={{ width: 200 }}></th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.channel_id}>
                  <td>
                    <a href={s.url ?? "#"} target="_blank" rel="noreferrer">
                      {s.title}
                    </a>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {s.days_since_last_upload ?? "—"}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {s.avg_vpd_recent != null
                      ? Math.round(s.avg_vpd_recent).toLocaleString("pt-BR")
                      : "—"}
                  </td>
                  <td className="muted" style={{ fontSize: 11 }}>
                    {s.signal ?? "—"}
                  </td>
                  <td className="muted" style={{ fontSize: 11 }}>{s.reason}</td>
                  <td>
                    <div className="row-actions">
                      <button
                        type="button"
                        className="btn-ghost"
                        onClick={() => onPause(s)}
                      >
                        Pausar
                      </button>
                      <button
                        type="button"
                        className="btn-ghost danger"
                        onClick={() => onRemove(s)}
                      >
                        Remover
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function BulkProgressBar({ progress }: { progress: BulkProgress }) {
  const { label, total, done, success, failed } = progress;
  const pct = total === 0 ? 0 : Math.round((done / total) * 100);
  const finished = done >= total;
  const stateClass = !finished
    ? "bulk-progress-running"
    : failed === 0
    ? "bulk-progress-ok"
    : success === 0
    ? "bulk-progress-fail"
    : "bulk-progress-partial";
  return (
    <div className={`bulk-progress ${stateClass}`} role="status" aria-live="polite">
      <div className="bulk-progress-row">
        <strong>{label}</strong>
        <span className="muted" style={{ fontSize: 12 }}>
          {done}/{total} processados ({pct}%)
          {failed > 0 && (
            <>
              {" · "}
              <span className="bulk-progress-fail-count">
                {failed} falha{failed > 1 ? "s" : ""}
              </span>
            </>
          )}
          {finished && " · concluído"}
        </span>
      </div>
      <div className="bulk-progress-track">
        <div
          className="bulk-progress-fill"
          style={{ width: `${pct}%` }}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}
