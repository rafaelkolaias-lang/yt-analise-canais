"use client";

import { useEffect, useState } from "react";

import { ChannelAvatar } from "@/components/ChannelAvatar";
import { VideoThumbnail } from "@/components/VideoThumbnail";
import {
  apiGet,
  type AnalyticsHighlights,
  type AnalyticsOverview,
  type HighlightKind,
} from "@/lib/api";

type Props = { overview: AnalyticsOverview | null };

type CardDef = {
  kind: HighlightKind;
  label: string;
  hint: string;
  count: (o: AnalyticsOverview) => number;
  /** Classe do sinal — pinta a borda esquerda do card (mesma paleta do Analytics). */
  signalClass: string;
};

const CARDS: CardDef[] = [
  {
    kind: "heating",
    label: "Aquecendo",
    hint: "VPD subindo forte",
    count: (o) => o.channels_accelerating,
    signalClass: "signal-heating",
  },
  {
    kind: "promising",
    label: "Promissores",
    hint: "pequenos com VPD alto",
    count: (o) => o.channels_promising,
    signalClass: "signal-promising",
  },
  {
    kind: "saturated",
    label: "Saturados",
    hint: "acima do limite",
    count: (o) => o.channels_saturated,
    signalClass: "signal-saturated",
  },
  {
    kind: "videos_accelerating",
    label: "Vídeos acelerando",
    hint: "VPD crescendo no último snapshot",
    count: (o) => o.videos_accelerating,
    signalClass: "signal-stable",
  },
];

const LIMIT = 50;

function fmtNumber(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return Math.round(v).toLocaleString("pt-BR");
}

function fmtDecimal(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
}

function fmtDelta(v: number | null | undefined): string | null {
  if (v === null || v === undefined || v === 0) return null;
  const sign = v > 0 ? "+" : "";
  return `${sign}${Math.round(v).toLocaleString("pt-BR")}`;
}

function fmtDateTime(s: string | null | undefined): string {
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

/** Link para a tela de Analytics já filtrada naquele canal (deep-link ?q=). */
function analyticsLink(title: string): string {
  return `/analytics?q=${encodeURIComponent(title)}`;
}

export function DashboardHighlights({ overview }: Props) {
  const [openKind, setOpenKind] = useState<HighlightKind | null>(null);
  const [data, setData] = useState<AnalyticsHighlights | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!openKind) return;
    let cancelled = false;
    async function load(kind: HighlightKind) {
      setLoading(true);
      setError(null);
      try {
        const res = await apiGet<AnalyticsHighlights>(
          `/api/analytics/highlights?kind=${kind}&status=active&limit=${LIMIT}`
        );
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) {
          setData(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load(openKind);
    return () => {
      cancelled = true;
    };
  }, [openKind]);

  const active = CARDS.find((c) => c.kind === openKind) ?? null;

  return (
    <section style={{ marginTop: 16 }}>
      <div className="card-grid" role="tablist" aria-label="Destaques do dashboard">
        {CARDS.map((card) => {
          const isOpen = card.kind === openKind;
          const count = overview ? card.count(overview) : null;
          return (
            <button
              key={card.kind}
              type="button"
              role="tab"
              aria-selected={isOpen}
              aria-expanded={isOpen}
              className={`card dash-highlight-card ${card.signalClass}${
                isOpen ? " is-open" : ""
              }`}
              onClick={() => setOpenKind(isOpen ? null : card.kind)}
            >
              <div className="muted">{card.label}</div>
              <div style={{ fontSize: 22, marginTop: 4 }}>{count ?? "—"}</div>
              <div className="muted" style={{ fontSize: 11 }}>
                {card.hint}
              </div>
              <div className="dash-highlight-cta">
                {isOpen ? "fechar lista ▲" : "ver lista ▼"}
              </div>
            </button>
          );
        })}
      </div>

      {active && (
        <div className="card" style={{ marginTop: 12 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              flexWrap: "wrap",
              marginBottom: 10,
            }}
          >
            <strong style={{ fontSize: 14 }}>{active.label}</strong>
            <span className="muted" style={{ fontSize: 11 }}>
              {loading
                ? "carregando…"
                : data
                ? `${data.total} no total${
                    data.total > LIMIT ? ` · mostrando os ${LIMIT} primeiros` : ""
                  } · apenas canais ativos`
                : ""}
            </span>
            {loading && <span className="spinner" aria-hidden />}
            <a
              href={
                active.kind === "videos_accelerating"
                  ? "/analytics"
                  : `/analytics?signal=${active.kind}`
              }
              className="btn-ghost"
              style={{ marginLeft: "auto", textDecoration: "none" }}
            >
              abrir no Analytics
            </a>
          </div>

          {error && (
            <div className="muted" style={{ fontSize: 12, color: "var(--danger)" }}>
              Falha ao carregar a lista: {error}
            </div>
          )}

          {!error && !loading && data && data.total === 0 && (
            <div className="muted" style={{ fontSize: 12 }}>
              Nenhum item nessa classificação agora.
            </div>
          )}

          {!error && data && data.total > 0 && (
            <div className="table-wrap">
              {active.kind === "videos_accelerating" ? (
                <VideosTable rows={data.videos} />
              ) : (
                <ChannelsTable rows={data.channels} />
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function ChannelsTable({
  rows,
}: {
  rows: AnalyticsHighlights["channels"];
}) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Canal</th>
          <th style={{ textAlign: "right" }}>Inscritos</th>
          <th style={{ textAlign: "right" }}>VPD recente</th>
          <th style={{ textAlign: "right" }}>Uploads/sem</th>
          <th style={{ textAlign: "right" }}>Oportunidade</th>
          <th>Por quê</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => {
          const delta = fmtDelta(c.delta_avg_vpd);
          return (
            <tr key={c.id}>
              <td>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <ChannelAvatar url={c.thumbnail_url} title={c.title} size={26} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      {c.is_favorite && <span title="Favorito">⭐</span>}
                      {c.url ? (
                        <a href={c.url} target="_blank" rel="noreferrer">
                          {c.title}
                        </a>
                      ) : (
                        c.title
                      )}
                    </div>
                    <div className="muted" style={{ fontSize: 10 }}>
                      medido em {fmtDateTime(c.captured_at)}
                    </div>
                  </div>
                </div>
              </td>
              <td style={{ textAlign: "right" }}>{fmtNumber(c.subscribers)}</td>
              <td style={{ textAlign: "right" }}>
                {fmtNumber(c.avg_vpd_recent)}
                {delta && (
                  <div
                    className="muted"
                    style={{
                      fontSize: 10,
                      color:
                        (c.delta_avg_vpd ?? 0) > 0 ? "var(--success)" : "var(--danger)",
                    }}
                  >
                    {delta}
                  </div>
                )}
              </td>
              <td style={{ textAlign: "right" }}>{fmtDecimal(c.uploads_per_week)}</td>
              <td style={{ textAlign: "right" }}>{c.opportunity_score}</td>
              <td className="muted" style={{ fontSize: 11, maxWidth: 320 }}>
                {c.signal_reason ?? "—"}
              </td>
              <td style={{ textAlign: "right" }}>
                <a
                  className="btn-ghost"
                  href={analyticsLink(c.title)}
                  style={{ textDecoration: "none", fontSize: 11, padding: "4px 8px" }}
                >
                  detalhes
                </a>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function VideosTable({ rows }: { rows: AnalyticsHighlights["videos"] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Vídeo</th>
          <th>Canal</th>
          <th style={{ textAlign: "right" }}>VPD agora</th>
          <th style={{ textAlign: "right" }}>VPD anterior</th>
          <th style={{ textAlign: "right" }}>Salto</th>
          <th style={{ textAlign: "right" }}>Views</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((v) => (
          <tr key={v.id}>
            <td>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <VideoThumbnail
                  url={v.thumbnail_url}
                  title={v.title}
                  width={72}
                  videoId={v.youtube_video_id}
                  watchUrl={v.url}
                />
                <div style={{ minWidth: 0 }}>
                  {v.url ? (
                    <a href={v.url} target="_blank" rel="noreferrer">
                      {v.title}
                    </a>
                  ) : (
                    v.title
                  )}
                  <div className="muted" style={{ fontSize: 10 }}>
                    visto em {fmtDateTime(v.last_seen_at)}
                  </div>
                </div>
              </div>
            </td>
            <td>
              <a href={analyticsLink(v.channel_title)}>{v.channel_title}</a>
            </td>
            <td style={{ textAlign: "right" }}>{fmtNumber(v.vpd_now)}</td>
            <td style={{ textAlign: "right" }}>{fmtNumber(v.vpd_prev)}</td>
            <td style={{ textAlign: "right", color: "var(--success)" }}>
              {fmtDelta(v.vpd_delta) ?? "—"}
            </td>
            <td style={{ textAlign: "right" }}>{fmtNumber(v.last_seen_views)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
