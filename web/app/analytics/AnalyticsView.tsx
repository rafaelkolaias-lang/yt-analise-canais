"use client";

import { useEffect, useState } from "react";

import { ChannelAvatar } from "@/components/ChannelAvatar";
import { ChannelNote, FavoriteStar } from "@/components/ChannelMetaControls";
import { SpikeAlertControl } from "@/components/SpikeAlertControl";
import { ChannelChart, type ChartBucket } from "@/components/ChannelChart";
import { ErrorCard } from "@/components/ErrorCard";
import { Skeleton } from "@/components/Skeleton";
import { VideosByChannelView } from "@/components/VideosByChannelView";
import {
  apiGet,
  type AnalyticsOverview,
  type ChannelAnalyticsBundle,
  type NicheRow,
  type PaginatedChannelAnalytics,
} from "@/lib/api";

type AnalyticsTab = "channels" | "videos";

type Props = {
  niches: NicheRow[];
};

const PAGE_SIZE_OPTIONS = [10, 20, 50] as const;
const DEFAULT_PAGE_SIZE = 10;

type StatusFilter = "active" | "paused" | "removed" | "all";

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "active", label: "Ativos" },
  { value: "paused", label: "Pausados" },
  { value: "removed", label: "Removidos" },
  { value: "all", label: "Todos" },
];

type SignalFilter =
  | "all"
  | "heating"
  | "promising"
  | "stable"
  | "saturated"
  | "unknown";

// Ordem reflete a prioridade do backend (melhor → pior). "Todos" fica
// primeiro pra ser o default visual.
const SIGNAL_OPTIONS: { value: SignalFilter; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "heating", label: "Aquecendo" },
  { value: "promising", label: "Promissor" },
  { value: "stable", label: "Estável" },
  { value: "saturated", label: "Saturado" },
  { value: "unknown", label: "Sem sinal" },
];

const BUCKET_OPTIONS: { value: ChartBucket; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "1d", label: "1 dia" },
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
];

type SortBy = "signal" | "score";

const SORT_OPTIONS: { value: SortBy; label: string }[] = [
  { value: "signal", label: "Sinal" },
  { value: "score", label: "Oportunidade" },
];

function scoreColor(score: number): string {
  if (score >= 70) return "#7ef0df"; // alto — verde-água
  if (score >= 45) return "#b9d0ff"; // médio — azul
  if (score >= 25) return "#ffd591"; // baixo — âmbar
  return "var(--text-dim)"; // muito baixo
}

function signalLabel(signal: string | null): string {
  switch (signal) {
    case "heating":
      return "aquecendo";
    case "promising":
      return "promissor";
    case "saturated":
      return "saturado";
    case "stable":
      return "estável";
    default:
      return "—";
  }
}

function fmtNumber(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR");
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

function consistencyLabel(label: string | null | undefined): string {
  switch (label) {
    case "forte":
      return "consistÃªncia forte";
    case "mista":
      return "consistÃªncia mista";
    case "fraca":
      return "consistÃªncia fraca";
    default:
      return "sem consistÃªncia";
  }
}

export function AnalyticsView({ niches }: Props) {
  const [activeTab, setActiveTab] = useState<AnalyticsTab>("channels");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");
  const [signalFilter, setSignalFilter] = useState<SignalFilter>("all");
  const [sortBy, setSortBy] = useState<SortBy>("signal");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState(""); // versão "debounced" enviada à API
  const [chartBucket, setChartBucket] = useState<ChartBucket>("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);
  const [data, setData] = useState<PaginatedChannelAnalytics | null>(null);
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  // Merge de metadados (estrela/observação) devolvidos pelo PATCH /meta no
  // canal correspondente dentro da página atual.
  const onChannelMetaChanged = (updated: {
    id: number;
    is_favorite: boolean;
    notes: string | null;
  }) =>
    setData((prev) =>
      prev
        ? {
            ...prev,
            items: prev.items.map((b) =>
              b.channel.id === updated.id
                ? {
                    ...b,
                    channel: {
                      ...b.channel,
                      is_favorite: updated.is_favorite,
                      notes: updated.notes,
                    },
                  }
                : b
            ),
          }
        : prev
    );

  // Deep-link: /analytics?q=<canal> (usado pelo card de pico de views e pelo
  // popup do app do Windows) já abre com a busca preenchida e filtrada.
  useEffect(() => {
    const initial = new URLSearchParams(window.location.search).get("q");
    if (initial) {
      setSearch(initial);
      setQ(initial);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [overviewResp, channelsResp] = await Promise.all([
          apiGet<AnalyticsOverview>(
            `/api/analytics/overview?status=${statusFilter}`
          ),
          apiGet<PaginatedChannelAnalytics>(
            `/api/analytics/channels?page=${page}&page_size=${pageSize}&status=${statusFilter}&signal=${signalFilter}&sort=${sortBy}&q=${encodeURIComponent(q)}`
          ),
        ]);
        if (!cancelled) {
          setOverview(overviewResp);
          setData(channelsResp);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [page, pageSize, statusFilter, signalFilter, sortBy, q, reloadTick]);

  // Busca com debounce: digita e em 300ms a lista filtra (volta pra página 1).
  useEffect(() => {
    const t = setTimeout(() => {
      const next = search.trim();
      setQ((prev) => {
        if (prev !== next) setPage(1);
        return next;
      });
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const totalPages = data?.total_pages ?? 0;
  const total = data?.total ?? 0;
  const items: ChannelAnalyticsBundle[] = data?.items ?? [];

  // Se total_pages mudar (ex: usuário removeu canais em outra aba) e a página
  // atual ficar fora do range, volta pra última página válida.
  useEffect(() => {
    if (totalPages > 0 && page > totalPages) {
      setPage(totalPages);
    }
  }, [totalPages, page]);

  const skeletonCount = Math.min(pageSize, total > 0 ? total : pageSize);

  return (
    <>
      {/* Abas principais */}
      <section
        className="card"
        style={{
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        {(
          [
            { value: "channels", label: "Canais" },
            { value: "videos", label: "Vídeos por canal" },
          ] as { value: AnalyticsTab; label: string }[]
        ).map((tab) => (
          <button
            key={tab.value}
            type="button"
            onClick={() => setActiveTab(tab.value)}
            className={activeTab === tab.value ? "btn-primary" : "btn-ghost"}
            style={{ fontSize: 13, padding: "6px 16px" }}
          >
            {tab.label}
          </button>
        ))}
      </section>

      {activeTab === "videos" && <VideosByChannelView />}

      {activeTab === "channels" && (
        <>
      {/* Barra de busca por nome do canal */}
      <section className="card" style={{ marginBottom: 16 }}>
        <input
          type="text"
          className="input"
          placeholder="Buscar canal por nome…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Buscar canal por nome"
          style={{ width: "100%" }}
        />
        {q && (
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
            {total} resultado(s) para “{q}”
          </div>
        )}
      </section>

      {/* Barra de filtro de status */}
      <section
        className="card"
        style={{
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 500 }}>Status do canal</div>
        <div role="tablist" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {STATUS_OPTIONS.map((opt) => {
            const active = opt.value === statusFilter;
            return (
              <button
                key={opt.value}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => {
                  if (opt.value !== statusFilter) {
                    setPage(1);
                    setStatusFilter(opt.value);
                  }
                }}
                className={active ? "btn-primary" : "btn-ghost"}
                style={{ fontSize: 12, padding: "6px 12px" }}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        <span className="muted" style={{ fontSize: 11, marginLeft: "auto" }}>
          mostrando {STATUS_OPTIONS.find((o) => o.value === statusFilter)?.label.toLowerCase()}
        </span>
      </section>

      {/* Barra de filtro de sinal — ordenacao padrao da lista vem do
          melhor para o pior (heating > promising > stable > saturated >
          sem sinal) e este filtro restringe a apenas um sinal quando
          necessario. */}
      <section
        className="card"
        style={{
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 500 }}>Sinal</div>
        <div role="tablist" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {SIGNAL_OPTIONS.map((opt) => {
            const active = opt.value === signalFilter;
            return (
              <button
                key={opt.value}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => {
                  if (opt.value !== signalFilter) {
                    setPage(1);
                    setSignalFilter(opt.value);
                  }
                }}
                className={active ? "btn-primary" : "btn-ghost"}
                style={{ fontSize: 12, padding: "6px 12px" }}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        <span className="muted" style={{ fontSize: 11, marginLeft: "auto" }}>
          {signalFilter === "all"
            ? "ordenado do melhor para o pior"
            : `apenas ${SIGNAL_OPTIONS.find((o) => o.value === signalFilter)?.label.toLowerCase()}`}
        </span>
      </section>

      {/* Barra de ordenacao — por sinal (default) ou por score de oportunidade */}
      <section
        className="card"
        style={{
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 500 }}>Ordenar por</div>
        <div role="tablist" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {SORT_OPTIONS.map((opt) => {
            const active = opt.value === sortBy;
            return (
              <button
                key={opt.value}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => {
                  if (opt.value !== sortBy) {
                    setPage(1);
                    setSortBy(opt.value);
                  }
                }}
                className={active ? "btn-primary" : "btn-ghost"}
                style={{ fontSize: 12, padding: "6px 12px" }}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        <span className="muted" style={{ fontSize: 11, marginLeft: "auto" }}>
          {sortBy === "score"
            ? "maior score de oportunidade primeiro"
            : "melhor sinal primeiro"}
        </span>
      </section>

      {/* Barra de granularidade dos graficos */}
      <section
        className="card"
        style={{
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 500 }}>Granularidade dos gráficos</div>
        <div role="tablist" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {BUCKET_OPTIONS.map((opt) => {
            const active = opt.value === chartBucket;
            return (
              <button
                key={opt.value}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => {
                  if (opt.value !== chartBucket) setChartBucket(opt.value);
                }}
                className={active ? "btn-primary" : "btn-ghost"}
                style={{ fontSize: 12, padding: "6px 12px" }}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        <span className="muted" style={{ fontSize: 11, marginLeft: "auto" }}>
          {chartBucket === "all"
            ? "todos os snapshots"
            : `1 ponto por ${BUCKET_OPTIONS.find((o) => o.value === chartBucket)?.label.toLowerCase()}`}
        </span>
      </section>

      {/* Cards de overview */}
      <section className="analytics-overview-grid">
        <div className="card">
          <div className="muted">Aquecendo</div>
          <div style={{ fontSize: 28, marginTop: 4 }}>
            {overview?.channels_accelerating ?? "—"}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>
            inscritos + VPD crescendo
          </div>
        </div>
        <div className="card">
          <div className="muted">Promissores</div>
          <div style={{ fontSize: 28, marginTop: 4 }}>
            {overview?.channels_promising ?? "—"}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>
            canais dark (pequenos com VPD alto)
          </div>
        </div>
        <div className="card">
          <div className="muted">Saturados</div>
          <div style={{ fontSize: 28, marginTop: 4 }}>
            {overview?.channels_saturated ?? "—"}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>
            VPD médio acima do limite
          </div>
        </div>
        <div className="card">
          <div className="muted">Vídeos acelerando</div>
          <div style={{ fontSize: 28, marginTop: 4 }}>
            {overview?.videos_accelerating ?? "—"}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>
            VPD do último &gt; penúltimo snapshot
          </div>
        </div>
      </section>

      {/* Erro de carregamento */}
      {error && (
        <div style={{ marginBottom: 16 }}>
          <ErrorCard
            message={error}
            onRetry={() => setReloadTick((n) => n + 1)}
          />
        </div>
      )}

      {/* Lista de canais */}
      {!error && total === 0 && !loading ? (
        <div className="card">
          <p className="muted" style={{ margin: 0 }}>
            {statusFilter === "active" ? (
              <>
                Nenhum canal ativo. Adicione canais em{" "}
                <a href="/monitoramento">Monitoramento</a> ou{" "}
                <a href="/descoberta">Descoberta</a>, ou troque o filtro acima.
              </>
            ) : (
              <>Nenhum canal corresponde ao filtro selecionado.</>
            )}
          </p>
        </div>
      ) : loading ? (
        <>
          {Array.from({ length: skeletonCount }).map((_, idx) => (
            <section key={idx} className="analytics-channel-card">
              <div className="analytics-channel-header">
                <div style={{ flex: 1 }}>
                  <Skeleton width="45%" height={18} />
                  <div style={{ marginTop: 6 }}>
                    <Skeleton width="70%" height={12} />
                  </div>
                </div>
                <Skeleton width={80} height={20} radius={999} />
              </div>
              <div className="analytics-charts-grid charts-3-2">
                {[0, 1, 2, 3, 4].map((i) => (
                  <div key={i} className="analytics-chart-box">
                    <Skeleton width="40%" height={11} />
                    <div style={{ marginTop: 8 }}>
                      <Skeleton width="100%" height={130} radius={6} />
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </>
      ) : (
        items.map(
          ({
            channel,
            opportunity_score,
            summary,
            subscribers_series,
            views_series,
            vpd_series,
            channel_vpd_series,
            uploads_series,
          }) => {
            const signal = summary?.signal ?? null;
            const signalClass = signal ? `signal-${signal}` : "signal-unknown";
            return (
              <section
                key={channel.id}
                className={`analytics-channel-card ${signalClass}`}
              >
                <div className="analytics-channel-header">
                  <div
                    style={{ display: "flex", gap: 12, flex: 1, minWidth: 0 }}
                  >
                    <ChannelAvatar
                      url={channel.thumbnail_url}
                      title={channel.title}
                      size={56}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <h3
                        style={{
                          margin: 0,
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                        }}
                      >
                        <FavoriteStar
                          channel={channel}
                          onChanged={onChannelMetaChanged}
                        />
                        {channel.url ? (
                          <a href={channel.url} target="_blank" rel="noreferrer">
                            {channel.title}
                          </a>
                        ) : (
                          channel.title
                        )}
                      </h3>
                      <div className="muted" style={{ fontSize: 12 }}>
                        {fmtNumber(summary?.subscribers.current)} inscritos ·{" "}
                        7d {fmtPct(summary?.subscribers.pct_7d)} ·{" "}
                        30d {fmtPct(summary?.subscribers.pct_30d)} ·{" "}
                        90d {fmtPct(summary?.subscribers.pct_90d)}
                        {summary?.uploads_per_week != null && (
                          <> · {summary.uploads_per_week} uploads/sem</>
                        )}
                      </div>
                      <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                        mediana dos últimos {summary?.recent_uploads_considered ?? 0} uploads:{" "}
                        {fmtNumber(summary?.median_recent_views)} views · subs{" "}
                        {consistencyLabel(summary?.subscribers_consistency?.label)} · views{" "}
                        {consistencyLabel(summary?.views_consistency?.label)}
                      </div>
                      <ChannelNote
                        channel={channel}
                        onChanged={onChannelMetaChanged}
                      />
                      {summary?.signal_reason && (
                        <div
                          className="muted"
                          style={{ fontSize: 11, marginTop: 4 }}
                        >
                          {summary.signal_reason}
                        </div>
                      )}
                      {summary?.breakout_candidate && summary.breakout_reason && (
                        <div
                          style={{
                            marginTop: 6,
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 8,
                            padding: "4px 8px",
                            borderRadius: 999,
                            background: "rgba(45, 212, 191, 0.12)",
                            color: "#7ef0df",
                            fontSize: 11,
                          }}
                        >
                          Canal Viral
                          <span style={{ color: "var(--text-dim)" }}>
                            {summary.breakout_reason}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "flex-end",
                      gap: 6,
                    }}
                  >
                    <span
                      className="opportunity-badge"
                      title="Score de oportunidade (0–100): combina sinal, momento do VPD e crescimento de inscritos."
                      style={{ color: scoreColor(opportunity_score) }}
                    >
                      <strong style={{ fontSize: 16 }}>{opportunity_score}</strong>
                      <span style={{ fontSize: 9 }}>OPORTUNIDADE</span>
                    </span>
                    <span className={`status-pill ${signalClass}`}>
                      {signalLabel(signal)}
                    </span>
                    <SpikeAlertControl channel={channel} />
                  </div>
                </div>

                <div className="analytics-charts-grid charts-3-2">
                  <ChannelChart
                    title="Inscritos"
                    data={subscribers_series}
                    color="#2dd4bf"
                    bucket={chartBucket}
                    aggregation="last"
                  />
                  <ChannelChart
                    title="Views totais"
                    data={views_series}
                    bucket={chartBucket}
                    aggregation="last"
                  />
                  <ChannelChart
                    title="Uploads/semana"
                    data={uploads_series}
                    kind="bar"
                    color="#a78bfa"
                    formatValue={(v) => v.toFixed(1)}
                    bucket={chartBucket}
                    aggregation="avg"
                  />
                  <ChannelChart
                    title="VPD do canal"
                    data={channel_vpd_series}
                    color="#fb7185"
                    bucket={chartBucket}
                    aggregation="avg"
                  />
                  <ChannelChart
                    title="VPD dos últimos 10 uploads"
                    data={vpd_series}
                    color="#f59e0b"
                    bucket={chartBucket}
                    aggregation="avg"
                  />
                </div>
              </section>
            );
          }
        )
      )}

      {/* Controles de paginação */}
      {total > 0 && (
        <div
          className="analytics-pagination"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            marginTop: 16,
            flexWrap: "wrap",
          }}
        >
          <div className="muted" style={{ fontSize: 12 }}>
            {total} canais · página {data?.page ?? page} de {totalPages || 1}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <label
              className="muted"
              style={{ fontSize: 12, display: "flex", gap: 6 }}
            >
              por página
              <select
                value={pageSize}
                onChange={(e) => {
                  setPage(1);
                  setPageSize(Number(e.target.value));
                }}
                disabled={loading}
              >
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="btn"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={loading || page <= 1}
            >
              Anterior
            </button>
            <button
              className="btn"
              onClick={() => setPage((p) => p + 1)}
              disabled={loading || page >= (totalPages || 1)}
            >
              Próxima
            </button>
          </div>
        </div>
      )}

      {/* Nichos */}
      {niches.length > 0 && (
        <section style={{ marginTop: 24 }}>
          <h3 style={{ marginBottom: 8 }}>Nichos</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Tag</th>
                  <th>Canais</th>
                  <th>Inscritos médios</th>
                  <th>VPD médio</th>
                </tr>
              </thead>
              <tbody>
                {niches.map((n) => (
                  <tr key={n.tag_id}>
                    <td>{n.tag_name}</td>
                    <td>{n.channels_count}</td>
                    <td>{fmtNumber(n.avg_subscribers)}</td>
                    <td>{fmtNumber(n.avg_vpd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
        </>
      )}
    </>
  );
}
