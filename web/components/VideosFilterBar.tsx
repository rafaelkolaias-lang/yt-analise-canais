"use client";

import { useState } from "react";

import type { MonitoredVideo } from "@/lib/api";

export type VideoSortKey =
  | "title_asc"
  | "title_desc"
  | "views_desc"
  | "views_asc"
  | "vpd_desc"
  | "vpd_asc"
  | "first_vpd_desc"
  | "added_desc"
  | "added_asc"
  | "last_sync_desc";

export type VideoStatusFilter = "all" | "active" | "paused" | "removed";
export type VideoSourceFilter = "all" | "discovery" | "best_from_channel";

export type VideoFilters = {
  search: string;
  status: VideoStatusFilter;
  source: VideoSourceFilter;
  minViews: string;
  maxViews: string;
  minVpd: string;
  maxVpd: string;
  addedFrom: string;
  addedTo: string;
  sort: VideoSortKey;
};

export const DEFAULT_VIDEO_FILTERS: VideoFilters = {
  search: "",
  status: "all",
  source: "all",
  minViews: "",
  maxViews: "",
  minVpd: "",
  maxVpd: "",
  addedFrom: "",
  addedTo: "",
  sort: "vpd_desc",
};

const SORT_LABELS: Record<VideoSortKey, string> = {
  title_asc: "Título (A→Z)",
  title_desc: "Título (Z→A)",
  views_desc: "Views (maior)",
  views_asc: "Views (menor)",
  vpd_desc: "VPD atual (maior)",
  vpd_asc: "VPD atual (menor)",
  first_vpd_desc: "VPD inicial (maior)",
  added_desc: "Adicionado (mais recente)",
  added_asc: "Adicionado (mais antigo)",
  last_sync_desc: "Último sync (mais recente)",
};

type Props = {
  filters: VideoFilters;
  onChange: (next: VideoFilters) => void;
  totalCount: number;
  filteredCount: number;
  /**
   * Quando true, mostra o dropdown de ordenação inline na barra. Útil pra
   * modo grade onde não há header de coluna pra clicar. No modo lista,
   * passar `false` — a ordenação acontece nos `<th>` da tabela.
   */
  showSortDropdown?: boolean;
};

export function VideosFilterBar({
  filters,
  onChange,
  totalCount,
  filteredCount,
  showSortDropdown = false,
}: Props) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const set = (patch: Partial<VideoFilters>) =>
    onChange({ ...filters, ...patch });

  const isFiltered = filteredCount !== totalCount;

  return (
    <div className="filter-bar">
      <input
        type="text"
        className="input filter-bar-search"
        placeholder="Buscar por título..."
        value={filters.search}
        onChange={(e) => set({ search: e.target.value })}
      />

      <select
        value={filters.status}
        onChange={(e) =>
          set({ status: e.target.value as VideoStatusFilter })
        }
        title="Status"
      >
        <option value="all">Status: todos</option>
        <option value="active">Status: active</option>
        <option value="paused">Status: paused</option>
        <option value="removed">Status: removed</option>
      </select>

      <select
        value={filters.source}
        onChange={(e) =>
          set({ source: e.target.value as VideoSourceFilter })
        }
        title="Origem"
      >
        <option value="all">Origem: todas</option>
        <option value="discovery">discovery</option>
        <option value="best_from_channel">best_from_channel</option>
      </select>

      {showSortDropdown && (
        <select
          value={filters.sort}
          onChange={(e) => set({ sort: e.target.value as VideoSortKey })}
          title="Ordenar"
        >
          {(Object.keys(SORT_LABELS) as VideoSortKey[]).map((k) => (
            <option key={k} value={k}>
              {SORT_LABELS[k]}
            </option>
          ))}
        </select>
      )}

      <button
        type="button"
        className="btn-ghost"
        onClick={() => setShowAdvanced((v) => !v)}
      >
        {showAdvanced ? "Menos" : "Mais filtros"}
      </button>

      <div className="filter-bar-spacer" />

      <span className="filter-bar-count">
        {isFiltered
          ? `Mostrando ${filteredCount} de ${totalCount}`
          : `${totalCount} vídeos`}
      </span>

      {isFiltered && (
        <button
          type="button"
          className="btn-ghost"
          onClick={() => onChange(DEFAULT_VIDEO_FILTERS)}
          title="Limpar filtros"
        >
          Limpar
        </button>
      )}

      {showAdvanced && (
        <div className="filter-bar-advanced">
          <label>
            Views:
            <input
              type="number"
              className="input"
              placeholder="min"
              value={filters.minViews}
              onChange={(e) => set({ minViews: e.target.value })}
            />
            a
            <input
              type="number"
              className="input"
              placeholder="max"
              value={filters.maxViews}
              onChange={(e) => set({ maxViews: e.target.value })}
            />
          </label>

          <label>
            VPD atual:
            <input
              type="number"
              className="input"
              placeholder="min"
              value={filters.minVpd}
              onChange={(e) => set({ minVpd: e.target.value })}
            />
            a
            <input
              type="number"
              className="input"
              placeholder="max"
              value={filters.maxVpd}
              onChange={(e) => set({ maxVpd: e.target.value })}
            />
          </label>

          <label>
            Adicionado:
            <input
              type="date"
              className="input"
              value={filters.addedFrom}
              onChange={(e) => set({ addedFrom: e.target.value })}
            />
            a
            <input
              type="date"
              className="input"
              value={filters.addedTo}
              onChange={(e) => set({ addedTo: e.target.value })}
            />
          </label>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Aplicação de filtros + ordenação
// =============================================================================
function parseNum(s: string): number | null {
  if (!s.trim()) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function parseDateStart(s: string): number | null {
  if (!s) return null;
  const t = new Date(s + "T00:00:00").getTime();
  return Number.isFinite(t) ? t : null;
}

function parseDateEnd(s: string): number | null {
  if (!s) return null;
  const t = new Date(s + "T23:59:59").getTime();
  return Number.isFinite(t) ? t : null;
}

export function applyVideoFilters(
  list: MonitoredVideo[],
  f: VideoFilters
): MonitoredVideo[] {
  const search = f.search.trim().toLowerCase();
  const minViews = parseNum(f.minViews);
  const maxViews = parseNum(f.maxViews);
  const minVpd = parseNum(f.minVpd);
  const maxVpd = parseNum(f.maxVpd);
  const addedFrom = parseDateStart(f.addedFrom);
  const addedTo = parseDateEnd(f.addedTo);

  let filtered = list.filter((v) => {
    if (search && !v.title.toLowerCase().includes(search)) return false;
    if (f.status !== "all" && v.status !== f.status) return false;
    if (f.source !== "all" && (v.tracking_source ?? "") !== f.source)
      return false;

    const views = v.last_seen_views ?? 0;
    if (minViews !== null && views < minViews) return false;
    if (maxViews !== null && views > maxViews) return false;

    const vpd = v.last_seen_vpd ?? 0;
    if (minVpd !== null && vpd < minVpd) return false;
    if (maxVpd !== null && vpd > maxVpd) return false;

    if (addedFrom !== null || addedTo !== null) {
      const added = new Date(v.first_tracked_at).getTime();
      if (addedFrom !== null && added < addedFrom) return false;
      if (addedTo !== null && added > addedTo) return false;
    }

    return true;
  });

  filtered = sortVideos(filtered, f.sort);
  return filtered;
}

function sortVideos(list: MonitoredVideo[], sort: VideoSortKey): MonitoredVideo[] {
  const cmp = (a: number | null | undefined, b: number | null | undefined) => {
    const av = a ?? -Infinity;
    const bv = b ?? -Infinity;
    return av < bv ? -1 : av > bv ? 1 : 0;
  };
  const arr = [...list];
  switch (sort) {
    case "title_asc":
      arr.sort((a, b) => a.title.localeCompare(b.title, "pt-BR"));
      break;
    case "title_desc":
      arr.sort((a, b) => b.title.localeCompare(a.title, "pt-BR"));
      break;
    case "views_desc":
      arr.sort((a, b) => -cmp(a.last_seen_views, b.last_seen_views));
      break;
    case "views_asc":
      arr.sort((a, b) => cmp(a.last_seen_views, b.last_seen_views));
      break;
    case "vpd_desc":
      arr.sort((a, b) => -cmp(a.last_seen_vpd, b.last_seen_vpd));
      break;
    case "vpd_asc":
      arr.sort((a, b) => cmp(a.last_seen_vpd, b.last_seen_vpd));
      break;
    case "first_vpd_desc":
      arr.sort((a, b) => -cmp(a.first_tracked_vpd, b.first_tracked_vpd));
      break;
    case "added_desc":
      arr.sort(
        (a, b) =>
          new Date(b.first_tracked_at).getTime() -
          new Date(a.first_tracked_at).getTime()
      );
      break;
    case "added_asc":
      arr.sort(
        (a, b) =>
          new Date(a.first_tracked_at).getTime() -
          new Date(b.first_tracked_at).getTime()
      );
      break;
    case "last_sync_desc":
      arr.sort((a, b) => {
        const av = a.last_seen_at ? new Date(a.last_seen_at).getTime() : 0;
        const bv = b.last_seen_at ? new Date(b.last_seen_at).getTime() : 0;
        return bv - av;
      });
      break;
  }
  return arr;
}
