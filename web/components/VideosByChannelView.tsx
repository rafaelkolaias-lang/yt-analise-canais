"use client";

import { useEffect, useState } from "react";

import { ChannelAvatar } from "@/components/ChannelAvatar";
import { ChannelChart, type ChartBucket } from "@/components/ChannelChart";
import { ErrorCard } from "@/components/ErrorCard";
import { Skeleton } from "@/components/Skeleton";
import {
  apiGet,
  type ChannelVideoBundle,
  type PaginatedVideosByChannel,
  type VideoAnalyticsItem,
} from "@/lib/api";

type StatusFilter = "active" | "paused" | "removed" | "all";

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "active", label: "Ativos" },
  { value: "paused", label: "Pausados" },
  { value: "removed", label: "Removidos" },
  { value: "all", label: "Todos" },
];

const BUCKET_OPTIONS: { value: ChartBucket; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "1d", label: "1 dia" },
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
];

function fmtNumber(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR");
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}

function VideoRow({
  video,
  bucket,
}: {
  video: VideoAnalyticsItem;
  bucket: ChartBucket;
}) {
  const [expanded, setExpanded] = useState(false);
  const isUnavailable = !!video.unavailable_reason;

  return (
    <div
      style={{
        borderTop: "1px solid var(--border)",
        padding: "10px 0",
      }}
    >
      <div
        style={{
          display: "flex",
          gap: 10,
          alignItems: "flex-start",
          cursor: "pointer",
        }}
        onClick={() => setExpanded((v) => !v)}
      >
        {video.thumbnail_url && (
          <img
            src={video.thumbnail_url}
            alt=""
            style={{
              width: 80,
              height: 45,
              objectFit: "cover",
              borderRadius: 4,
              flexShrink: 0,
              opacity: isUnavailable ? 0.5 : 1,
            }}
          />
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontWeight: 500,
              fontSize: 13,
              display: "flex",
              gap: 8,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            {video.url ? (
              <a
                href={video.url}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                style={{ color: isUnavailable ? "var(--text-dim)" : undefined }}
              >
                {video.title}
              </a>
            ) : (
              <span style={{ color: isUnavailable ? "var(--text-dim)" : undefined }}>
                {video.title}
              </span>
            )}
            {isUnavailable && (
              <span
                style={{
                  fontSize: 10,
                  padding: "2px 6px",
                  borderRadius: 999,
                  background: "rgba(239,68,68,0.12)",
                  color: "#ef4444",
                  flexShrink: 0,
                }}
              >
                {video.unavailable_reason}
              </span>
            )}
            {video.status !== "active" && !isUnavailable && (
              <span
                style={{
                  fontSize: 10,
                  padding: "2px 6px",
                  borderRadius: 999,
                  background: "var(--bg)",
                  color: "var(--text-dim)",
                  border: "1px solid var(--border)",
                  flexShrink: 0,
                }}
              >
                {video.status}
              </span>
            )}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 3 }}>
            VPD atual: {fmtNumber(video.last_seen_vpd)} · Views:{" "}
            {fmtNumber(video.last_seen_views)} · 1ª coleta: {fmtDate(video.first_tracked_at)}
            {video.first_tracked_vpd != null && (
              <> · VPD inicial: {fmtNumber(video.first_tracked_vpd)}</>
            )}
          </div>
        </div>
        <button
          className="btn-ghost"
          style={{ fontSize: 11, padding: "4px 8px", flexShrink: 0 }}
          onClick={(e) => {
            e.stopPropagation();
            setExpanded((v) => !v);
          }}
        >
          {expanded ? "▲ ocultar" : "▼ gráficos"}
        </button>
      </div>

      {expanded && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 8,
            marginTop: 10,
          }}
        >
          <ChannelChart
            title="VPD"
            data={video.vpd_series}
            color="#f59e0b"
            bucket={bucket}
            aggregation="avg"
          />
          <ChannelChart
            title="Views"
            data={video.views_series}
            bucket={bucket}
            aggregation="last"
          />
        </div>
      )}
    </div>
  );
}

function ChannelGroup({
  bundle,
  bucket,
}: {
  bundle: ChannelVideoBundle;
  bucket: ChartBucket;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const { channel, videos } = bundle;

  return (
    <section className="analytics-channel-card" style={{ marginBottom: 12 }}>
      <div
        className="analytics-channel-header"
        style={{ cursor: "pointer" }}
        onClick={() => setCollapsed((v) => !v)}
      >
        <div style={{ display: "flex", gap: 12, flex: 1, minWidth: 0, alignItems: "center" }}>
          <ChannelAvatar url={channel.thumbnail_url} title={channel.title} size={40} />
          <div>
            <h3 style={{ margin: 0, fontSize: 14 }}>
              {channel.url ? (
                <a
                  href={channel.url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                >
                  {channel.title}
                </a>
              ) : (
                channel.title
              )}
            </h3>
            <div className="muted" style={{ fontSize: 11 }}>
              {videos.length} vídeo{videos.length !== 1 ? "s" : ""} monitorado
              {videos.length !== 1 ? "s" : ""}
            </div>
          </div>
        </div>
        <button
          className="btn-ghost"
          style={{ fontSize: 11, padding: "4px 8px" }}
          onClick={(e) => {
            e.stopPropagation();
            setCollapsed((v) => !v);
          }}
        >
          {collapsed ? "▼ expandir" : "▲ recolher"}
        </button>
      </div>

      {!collapsed && (
        <div style={{ paddingTop: 4 }}>
          {videos.length === 0 ? (
            <p className="muted" style={{ fontSize: 12, margin: "8px 0 0" }}>
              Nenhum vídeo monitorado neste canal.
            </p>
          ) : (
            videos.map((v) => <VideoRow key={v.id} video={v} bucket={bucket} />)
          )}
        </div>
      )}
    </section>
  );
}

export function VideosByChannelView() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");
  const [chartBucket, setChartBucket] = useState<ChartBucket>("all");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<PaginatedVideosByChannel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const resp = await apiGet<PaginatedVideosByChannel>(
          `/api/analytics/videos-by-channel?page=${page}&page_size=10&channel_status=${statusFilter}`
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
  }, [page, statusFilter, reloadTick]);

  const totalPages = data?.total_pages ?? 0;
  const total = data?.total ?? 0;

  useEffect(() => {
    if (totalPages > 0 && page > totalPages) setPage(totalPages);
  }, [totalPages, page]);

  return (
    <>
      {/* Filtro de status do canal */}
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
      </section>

      {/* Granularidade dos gráficos */}
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
          clique em "gráficos" num vídeo para ver as séries temporais
        </span>
      </section>

      {/* Erro */}
      {error && (
        <div style={{ marginBottom: 16 }}>
          <ErrorCard message={error} onRetry={() => setReloadTick((n) => n + 1)} />
        </div>
      )}

      {/* Conteúdo */}
      {loading ? (
        <>
          {Array.from({ length: 5 }).map((_, i) => (
            <section key={i} className="analytics-channel-card" style={{ marginBottom: 12 }}>
              <div className="analytics-channel-header">
                <Skeleton width="40%" height={16} />
                <Skeleton width={80} height={14} />
              </div>
            </section>
          ))}
        </>
      ) : !error && total === 0 ? (
        <div className="card">
          <p className="muted" style={{ margin: 0 }}>
            Nenhum canal com vídeos monitorados corresponde ao filtro.
          </p>
        </div>
      ) : (
        data?.items.map((bundle) => (
          <ChannelGroup key={bundle.channel.id} bundle={bundle} bucket={chartBucket} />
        ))
      )}

      {/* Paginação */}
      {total > 0 && (
        <div
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
            {total} canal{total !== 1 ? "is" : ""} · página {data?.page ?? page} de{" "}
            {totalPages || 1}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
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
    </>
  );
}
