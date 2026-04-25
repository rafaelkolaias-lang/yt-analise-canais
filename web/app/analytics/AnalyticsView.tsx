"use client";

import { useEffect, useState } from "react";

import { ChannelAvatar } from "@/components/ChannelAvatar";
import { ChannelChart } from "@/components/ChannelChart";
import { ErrorCard } from "@/components/ErrorCard";
import { Skeleton } from "@/components/Skeleton";
import {
  apiGet,
  type AnalyticsOverview,
  type ChannelAnalyticsBundle,
  type NicheRow,
  type PaginatedChannelAnalytics,
} from "@/lib/api";

type Props = {
  overview: AnalyticsOverview | null;
  niches: NicheRow[];
};

const PAGE_SIZE_OPTIONS = [10, 20, 50] as const;
const DEFAULT_PAGE_SIZE = 10;

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

export function AnalyticsView({ overview, niches }: Props) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);
  const [data, setData] = useState<PaginatedChannelAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const resp = await apiGet<PaginatedChannelAnalytics>(
          `/api/analytics/channels?page=${page}&page_size=${pageSize}`
        );
        if (!cancelled) setData(resp);
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
  }, [page, pageSize, reloadTick]);

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
            Nenhum canal monitorado ainda. Adicione canais em{" "}
            <a href="/monitoramento">Monitoramento</a> ou{" "}
            <a href="/descoberta">Descoberta</a>.
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
              <div className="analytics-charts-grid">
                {[0, 1, 2, 3].map((i) => (
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
            summary,
            subscribers_series,
            views_series,
            vpd_series,
            uploads_series,
          }) => {
            const signal = summary?.signal ?? null;
            const signalClass = signal ? `signal-${signal}` : "";
            return (
              <section key={channel.id} className="analytics-channel-card">
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
                      <h3 style={{ margin: 0 }}>
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
                        30d {fmtPct(summary?.subscribers.pct_30d)}
                        {summary?.uploads_per_week != null && (
                          <> · {summary.uploads_per_week} uploads/sem</>
                        )}
                      </div>
                      {summary?.signal_reason && (
                        <div
                          className="muted"
                          style={{ fontSize: 11, marginTop: 4 }}
                        >
                          {summary.signal_reason}
                        </div>
                      )}
                    </div>
                  </div>
                  <span className={`status-pill ${signalClass}`}>
                    {signalLabel(signal)}
                  </span>
                </div>

                <div className="analytics-charts-grid">
                  <ChannelChart title="Views totais" data={views_series} />
                  <ChannelChart
                    title="Inscritos"
                    data={subscribers_series}
                    color="#2dd4bf"
                  />
                  <ChannelChart
                    title="VPD recente"
                    data={vpd_series}
                    color="#f59e0b"
                  />
                  <ChannelChart
                    title="Uploads/semana"
                    data={uploads_series}
                    kind="bar"
                    color="#a78bfa"
                    formatValue={(v) => v.toFixed(1)}
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
  );
}
