"use client";

import { useEffect, useState } from "react";

import { ChannelChart } from "@/components/ChannelChart";
import { ErrorCard } from "@/components/ErrorCard";
import { Skeleton } from "@/components/Skeleton";
import {
  apiGet,
  type AnalyticsOverview,
  type ChannelAnalyticsSummary,
  type MonitoredChannel,
  type NicheRow,
  type TimeseriesPoint,
} from "@/lib/api";

type ChannelBundle = {
  channel: MonitoredChannel;
  summary: ChannelAnalyticsSummary | null;
  subs: TimeseriesPoint[];
  views: TimeseriesPoint[];
  vpd: TimeseriesPoint[];
  uploads: TimeseriesPoint[];
};

type Props = {
  overview: AnalyticsOverview | null;
  channels: MonitoredChannel[];
  niches: NicheRow[];
};

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

export function AnalyticsView({ overview, channels, niches }: Props) {
  const [bundles, setBundles] = useState<ChannelBundle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const loaded: ChannelBundle[] = await Promise.all(
          channels.map(async (ch) => {
            const [summary, subs, views, vpd, uploads] = await Promise.all([
              apiGet<ChannelAnalyticsSummary>(
                `/api/analytics/channels/${ch.id}/summary`
              ).catch(() => null),
              apiGet<TimeseriesPoint[]>(
                `/api/analytics/channels/${ch.id}/timeseries?metric=subscribers`
              ).catch(() => []),
              apiGet<TimeseriesPoint[]>(
                `/api/analytics/channels/${ch.id}/timeseries?metric=views_total`
              ).catch(() => []),
              apiGet<TimeseriesPoint[]>(
                `/api/analytics/channels/${ch.id}/timeseries?metric=avg_vpd_recent`
              ).catch(() => []),
              apiGet<TimeseriesPoint[]>(
                `/api/analytics/channels/${ch.id}/timeseries?metric=uploads_per_week`
              ).catch(() => []),
            ]);
            return { channel: ch, summary, subs, views, vpd, uploads };
          })
        );
        if (!cancelled) setBundles(loaded);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    if (channels.length > 0) {
      load();
    } else {
      setLoading(false);
    }
    return () => {
      cancelled = true;
    };
  }, [channels, reloadTick]);

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

      {/* Lista de canais */}
      {error && (
        <div style={{ marginBottom: 16 }}>
          <ErrorCard
            message={error}
            onRetry={() => setReloadTick((n) => n + 1)}
          />
        </div>
      )}

      {channels.length === 0 ? (
        <div className="card">
          <p className="muted" style={{ margin: 0 }}>
            Nenhum canal monitorado ainda. Adicione canais em{" "}
            <a href="/monitoramento">Monitoramento</a> ou{" "}
            <a href="/descoberta">Descoberta</a>.
          </p>
        </div>
      ) : loading ? (
        <>
          {channels.map((ch) => (
            <section key={ch.id} className="analytics-channel-card">
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
        bundles.map(({ channel, summary, subs, views, vpd, uploads }) => {
          const signal = summary?.signal ?? null;
          const signalClass = signal ? `signal-${signal}` : "";
          return (
            <section
              key={channel.id}
              className="analytics-channel-card"
            >
              <div className="analytics-channel-header">
                <div>
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
                <span className={`status-pill ${signalClass}`}>
                  {signalLabel(signal)}
                </span>
              </div>

              <div className="analytics-charts-grid">
                <ChannelChart title="Views totais" data={views} />
                <ChannelChart title="Inscritos" data={subs} color="#2dd4bf" />
                <ChannelChart title="VPD recente" data={vpd} color="#f59e0b" />
                <ChannelChart
                  title="Uploads/semana"
                  data={uploads}
                  kind="bar"
                  color="#a78bfa"
                  formatValue={(v) => v.toFixed(1)}
                />
              </div>
            </section>
          );
        })
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
