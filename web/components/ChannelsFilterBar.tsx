"use client";

import { useEffect, useRef, useState } from "react";

import type { MonitoredChannel } from "@/lib/api";

export type ChannelSortKey =
  | "title_asc"
  | "title_desc"
  | "subs_desc"
  | "subs_asc"
  | "delta_subs_desc"
  | "vpd_desc"
  | "vpd_asc"
  | "added_desc"
  | "added_asc"
  | "last_sync_desc";

export type ChannelStatusFilter = "all" | "active" | "paused" | "removed";

export type ChannelFilters = {
  search: string;
  status: ChannelStatusFilter;
  source: string; // '' = todos
  minSubs: string; // string em vez de number pra suportar campo vazio
  maxSubs: string;
  minVpd: string;
  maxVpd: string;
  addedFrom: string; // YYYY-MM-DD
  addedTo: string;
  sort: ChannelSortKey;
};

export const DEFAULT_CHANNEL_FILTERS: ChannelFilters = {
  search: "",
  status: "active",
  source: "",
  minSubs: "",
  maxSubs: "",
  minVpd: "",
  maxVpd: "",
  addedFrom: "",
  addedTo: "",
  sort: "vpd_desc",
};

const SORT_LABELS: Record<ChannelSortKey, string> = {
  title_asc: "Título (A→Z)",
  title_desc: "Título (Z→A)",
  subs_desc: "Inscritos (maior)",
  subs_asc: "Inscritos (menor)",
  delta_subs_desc: "Δ inscritos (maior)",
  vpd_desc: "VPD (maior)",
  vpd_asc: "VPD (menor)",
  added_desc: "Adicionado (recente)",
  added_asc: "Adicionado (antigo)",
  last_sync_desc: "Último sync (recente)",
};

type Props = {
  filters: ChannelFilters;
  onChange: (next: ChannelFilters) => void;
  totalCount: number;
  filteredCount: number;
  /** Lista de `source` distintos pra popular o dropdown. */
  availableSources: string[];
  /**
   * Quando true, mostra o select de ordenação inline na barra. Útil em
   * mobile, onde a tabela vira cards e os SortableHeader não existem.
   */
  showSortDropdown?: boolean;
};

export function ChannelsFilterBar({
  filters,
  onChange,
  totalCount,
  filteredCount,
  availableSources,
  showSortDropdown = false,
}: Props) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const set = (patch: Partial<ChannelFilters>) =>
    onChange({ ...filters, ...patch });

  // Busca com debounce: o input atualiza um estado local na hora, mas só
  // propaga pro filtro (que re-renderiza a lista inteira) após 250ms parado.
  const [searchInput, setSearchInput] = useState(filters.search);
  // Refs com os valores MAIS RECENTES de filters/onChange. O timeout do
  // debounce lê daqui ao disparar, em vez de capturar uma closure antiga —
  // assim ele aplica a busca sobre os filtros atuais e não reverte uma
  // mudança feita em outro campo (status, ordem, etc.) durante a espera.
  const filtersRef = useRef(filters);
  filtersRef.current = filters;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  // Sincroniza quando o filtro muda por fora (ex: botão "Limpar").
  useEffect(() => {
    setSearchInput(filters.search);
  }, [filters.search]);
  useEffect(() => {
    if (searchInput === filtersRef.current.search) return;
    const t = setTimeout(() => {
      onChangeRef.current({ ...filtersRef.current, search: searchInput });
    }, 250);
    return () => clearTimeout(t);
  }, [searchInput]);

  const isFiltered = filteredCount !== totalCount;

  return (
    <div className="filter-bar">
      <input
        type="text"
        className="input filter-bar-search"
        placeholder="Buscar por nome..."
        value={searchInput}
        onChange={(e) => setSearchInput(e.target.value)}
      />

      <select
        value={filters.status}
        onChange={(e) =>
          set({ status: e.target.value as ChannelStatusFilter })
        }
        title="Status"
      >
        <option value="all">Status: todos</option>
        <option value="active">Status: active</option>
        <option value="paused">Status: paused</option>
        <option value="removed">Status: removed</option>
      </select>

      {showSortDropdown && (
        <select
          value={filters.sort}
          onChange={(e) => set({ sort: e.target.value as ChannelSortKey })}
          title="Ordenar"
        >
          {(Object.keys(SORT_LABELS) as ChannelSortKey[]).map((k) => (
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
          : `${totalCount} canais`}
      </span>

      {isFiltered && (
        <button
          type="button"
          className="btn-ghost"
          onClick={() => onChange(DEFAULT_CHANNEL_FILTERS)}
          title="Limpar filtros"
        >
          Limpar
        </button>
      )}

      {showAdvanced && (
        <div className="filter-bar-advanced">
          <label>
            Inscritos:
            <input
              type="number"
              className="input"
              placeholder="min"
              value={filters.minSubs}
              onChange={(e) => set({ minSubs: e.target.value })}
            />
            a
            <input
              type="number"
              className="input"
              placeholder="max"
              value={filters.maxSubs}
              onChange={(e) => set({ maxSubs: e.target.value })}
            />
          </label>

          <label>
            VPD:
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

          {availableSources.length > 0 && (
            <label>
              Origem:
              <select
                value={filters.source}
                onChange={(e) => set({ source: e.target.value })}
              >
                <option value="">todas</option>
                {availableSources.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Aplicação de filtros + ordenação (lado do client)
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
  // fim do dia
  const t = new Date(s + "T23:59:59").getTime();
  return Number.isFinite(t) ? t : null;
}

export function applyChannelFilters(
  list: MonitoredChannel[],
  f: ChannelFilters
): MonitoredChannel[] {
  const search = f.search.trim().toLowerCase();
  const minSubs = parseNum(f.minSubs);
  const maxSubs = parseNum(f.maxSubs);
  const minVpd = parseNum(f.minVpd);
  const maxVpd = parseNum(f.maxVpd);
  const addedFrom = parseDateStart(f.addedFrom);
  const addedTo = parseDateEnd(f.addedTo);

  let filtered = list.filter((c) => {
    if (search && !c.title.toLowerCase().includes(search)) return false;
    if (f.status !== "all" && c.status !== f.status) return false;
    if (f.source && (c.source ?? "") !== f.source) return false;

    const subs = c.subscribers ?? 0;
    if (minSubs !== null && subs < minSubs) return false;
    if (maxSubs !== null && subs > maxSubs) return false;

    const vpd = c.avg_vpd_recent ?? 0;
    if (minVpd !== null && vpd < minVpd) return false;
    if (maxVpd !== null && vpd > maxVpd) return false;

    if (addedFrom !== null || addedTo !== null) {
      const added = new Date(c.created_at).getTime();
      if (addedFrom !== null && added < addedFrom) return false;
      if (addedTo !== null && added > addedTo) return false;
    }

    return true;
  });

  filtered = sortChannels(filtered, f.sort);
  return filtered;
}

function sortChannels(
  list: MonitoredChannel[],
  sort: ChannelSortKey
): MonitoredChannel[] {
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
    case "subs_desc":
      arr.sort((a, b) => -cmp(a.subscribers, b.subscribers));
      break;
    case "subs_asc":
      arr.sort((a, b) => cmp(a.subscribers, b.subscribers));
      break;
    case "delta_subs_desc":
      arr.sort((a, b) => -cmp(a.delta_subscribers, b.delta_subscribers));
      break;
    case "vpd_desc":
      arr.sort((a, b) => -cmp(a.avg_vpd_recent, b.avg_vpd_recent));
      break;
    case "vpd_asc":
      arr.sort((a, b) => cmp(a.avg_vpd_recent, b.avg_vpd_recent));
      break;
    case "added_desc":
      arr.sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      break;
    case "added_asc":
      arr.sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      );
      break;
    case "last_sync_desc":
      arr.sort((a, b) => {
        const av = a.last_snapshot_at ? new Date(a.last_snapshot_at).getTime() : 0;
        const bv = b.last_snapshot_at ? new Date(b.last_snapshot_at).getTime() : 0;
        return bv - av;
      });
      break;
  }
  return arr;
}
