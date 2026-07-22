"use client";

import { useCallback, useEffect, useState } from "react";

import { ChannelAvatar } from "@/components/ChannelAvatar";
import { ChannelChart } from "@/components/ChannelChart";
import { useConfirm } from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toaster";
import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  type CandidateChannel,
  type DeadChannelSuggestion,
  type MonitoredChannel,
  type MonitorSuggestion,
  type TimeseriesPoint,
} from "@/lib/api";

function fmtInt(v: number | null | undefined): string {
  return v != null ? Math.round(v).toLocaleString("pt-BR") : "—";
}

function describeError(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
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

// Séries dos gráficos de um candidato (mesmos endpoints do Analytics).
type CandidateSeries = {
  vpd: TimeseriesPoint[];
  views: TimeseriesPoint[];
  subs: TimeseriesPoint[];
};

export function SugestoesView() {
  const toast = useToast();
  const confirm = useConfirm();

  const [candidates, setCandidates] = useState<CandidateChannel[] | null>(null);
  const [toMonitor, setToMonitor] = useState<MonitorSuggestion[] | null>(null);
  const [toRemove, setToRemove] = useState<DeadChannelSuggestion[] | null>(null);
  const [seriesByChannel, setSeriesByChannel] = useState<
    Record<number, CandidateSeries>
  >({});
  const [loading, setLoading] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [cand, mon, rem] = await Promise.all([
        apiGet<CandidateChannel[]>("/api/suggestions/candidates"),
        apiGet<MonitorSuggestion[]>("/api/suggestions/to-monitor"),
        apiGet<DeadChannelSuggestion[]>("/api/suggestions/to-remove"),
      ]);
      setCandidates(cand);
      setToMonitor(mon);
      setToRemove(rem);

      // Gráficos dos candidatos: mesmas séries do Analytics, por canal.
      // Falha individual vira série vazia (o card mostra "sem dados").
      const entries = await Promise.all(
        cand.map(async (c) => {
          const base = `/api/analytics/channels/${c.channel_id}/timeseries`;
          const [vpd, views, subs] = await Promise.all([
            apiGet<TimeseriesPoint[]>(`${base}?metric=avg_vpd_recent`).catch(() => []),
            apiGet<TimeseriesPoint[]>(`${base}?metric=views_total`).catch(() => []),
            apiGet<TimeseriesPoint[]>(`${base}?metric=subscribers`).catch(() => []),
          ]);
          return [c.channel_id, { vpd, views, subs }] as const;
        })
      );
      setSeriesByChannel(Object.fromEntries(entries));
    } catch (e) {
      toast.error(`Falha ao carregar sugestões: ${describeError(e)}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  // ---- candidatos ----
  async function onPromoteCandidate(c: CandidateChannel) {
    try {
      await apiPost(`/api/suggestions/candidates/${c.channel_id}/promote`, {});
      toast.success(`"${c.title}" agora é monitorado.`);
      setCandidates((prev) =>
        prev ? prev.filter((x) => x.channel_id !== c.channel_id) : prev
      );
    } catch (e) {
      toast.error(describeError(e));
    }
  }

  async function onDismissCandidate(c: CandidateChannel) {
    if (
      !(await confirm({
        title: "Dispensar candidato",
        message: `Dispensar "${c.title}"? O histórico de observação é apagado e ele nunca mais será sugerido.`,
        confirmLabel: "Dispensar",
        danger: true,
      }))
    ) {
      return;
    }
    try {
      await apiPost(`/api/suggestions/candidates/${c.channel_id}/dismiss`, {});
      toast.success(`"${c.title}" dispensado.`);
      setCandidates((prev) =>
        prev ? prev.filter((x) => x.channel_id !== c.channel_id) : prev
      );
    } catch (e) {
      toast.error(describeError(e));
    }
  }

  // ---- sugestões "para monitorar" ----
  async function onMonitorSuggestion(s: MonitorSuggestion) {
    try {
      await apiPost<MonitoredChannel>("/api/monitoring/channels", {
        youtube_channel_id: s.youtube_channel_id,
      });
      toast.success(`Monitorando "${s.title}".`);
      setToMonitor((prev) =>
        prev ? prev.filter((x) => x.youtube_channel_id !== s.youtube_channel_id) : prev
      );
    } catch (e) {
      toast.error(describeError(e));
    }
  }

  async function onDismissSuggestion(s: MonitorSuggestion) {
    if (
      !(await confirm({
        title: "Dispensar sugestão",
        message: `Dispensar "${s.title}"? Ele entra na blacklist e nunca mais será sugerido.`,
        confirmLabel: "Dispensar",
        danger: true,
      }))
    ) {
      return;
    }
    try {
      await apiPost("/api/suggestions/dismiss", {
        youtube_channel_id: s.youtube_channel_id,
      });
      toast.success(`"${s.title}" dispensado.`);
      setToMonitor((prev) =>
        prev ? prev.filter((x) => x.youtube_channel_id !== s.youtube_channel_id) : prev
      );
    } catch (e) {
      toast.error(describeError(e));
    }
  }

  // ---- mortos ----
  async function onPauseDead(s: DeadChannelSuggestion) {
    try {
      await apiPatch(`/api/monitoring/channels/${s.channel_id}`, { status: "paused" });
      toast.success(`"${s.title}" pausado.`);
      setToRemove((prev) =>
        prev ? prev.filter((x) => x.channel_id !== s.channel_id) : prev
      );
    } catch (e) {
      toast.error(describeError(e));
    }
  }

  async function onRemoveDead(s: DeadChannelSuggestion) {
    if (
      !(await confirm({
        title: "Remover canal",
        message: `Remover "${s.title}" e todo o histórico de snapshots? O canal entrará na blacklist.`,
        confirmLabel: "Remover",
        danger: true,
      }))
    ) {
      return;
    }
    try {
      await apiDelete(`/api/monitoring/channels/${s.channel_id}`);
      toast.success(`"${s.title}" removido.`);
      setToRemove((prev) =>
        prev ? prev.filter((x) => x.channel_id !== s.channel_id) : prev
      );
    } catch (e) {
      toast.error(describeError(e));
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button
          type="button"
          className="btn-ghost"
          onClick={loadAll}
          disabled={loading}
        >
          {loading ? "..." : "Recarregar"}
        </button>
      </div>

      {/* ------------------- Candidatos em observação ------------------- */}
      <section className="card" style={{ background: "rgba(79, 140, 255, 0.05)" }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>
          Em observação automática{" "}
          <span className="muted" style={{ fontWeight: 400, fontSize: 11 }}>
            (as top sugestões entram aqui sozinhas após cada sync; o sistema
            acompanha o VPD delas e mostra quem está confirmando)
          </span>
        </h3>
      </section>
      {loading && candidates === null ? (
        <div className="muted" style={{ fontSize: 12 }}>carregando…</div>
      ) : !candidates || candidates.length === 0 ? (
        <div className="muted" style={{ fontSize: 12 }}>
          nenhum canal em observação ainda — após o próximo sync as melhores
          sugestões entram aqui automaticamente.
        </div>
      ) : (
        candidates.map((c) => {
          const signalClass = c.signal ? `signal-${c.signal}` : "signal-unknown";
          const series = seriesByChannel[c.channel_id];
          const up = (c.vpd_delta_pct ?? 0) > 0;
          const deltaColor =
            c.vpd_delta_pct == null
              ? "var(--text-dim)"
              : up
              ? "#4ade80"
              : "#f87171";
          return (
            <section
              key={c.channel_id}
              className={`analytics-channel-card ${signalClass}`}
            >
              <div className="analytics-channel-header">
                <div style={{ display: "flex", gap: 12, flex: 1, minWidth: 0 }}>
                  <ChannelAvatar
                    url={c.thumbnail_url}
                    title={c.title}
                    size={56}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <h3 style={{ margin: 0 }}>
                      {c.url ? (
                        <a href={c.url} target="_blank" rel="noreferrer">
                          {c.title}
                        </a>
                      ) : (
                        c.title
                      )}
                    </h3>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {fmtInt(c.subscribers)} inscritos · VPD inicial{" "}
                      {fmtInt(c.first_vpd)} → atual {fmtInt(c.last_vpd)}
                    </div>
                    <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                      em observação há {c.days_observed}d ·{" "}
                      {c.snapshots_count} snapshots
                    </div>
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
                    title="Evolução do VPD médio desde que o canal entrou em observação."
                    style={{ color: deltaColor }}
                  >
                    <strong style={{ fontSize: 16 }}>
                      {c.vpd_delta_pct == null
                        ? "…"
                        : `${up ? "+" : ""}${c.vpd_delta_pct.toLocaleString("pt-BR")}%`}
                    </strong>
                    <span style={{ fontSize: 9 }}>EVOLUÇÃO VPD</span>
                  </span>
                  <span className={`status-pill ${signalClass}`}>
                    {signalLabel(c.signal)}
                  </span>
                  <div className="row-actions">
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={() => onPromoteCandidate(c)}
                    >
                      Monitorar
                    </button>
                    <button
                      type="button"
                      className="btn-ghost danger"
                      onClick={() => onDismissCandidate(c)}
                    >
                      Dispensar
                    </button>
                  </div>
                </div>
              </div>

              <div className="analytics-charts-grid">
                <ChannelChart
                  title="VPD recente"
                  data={series?.vpd ?? []}
                  color="#f59e0b"
                  aggregation="avg"
                />
                <ChannelChart
                  title="Views totais"
                  data={series?.views ?? []}
                  aggregation="last"
                />
                <ChannelChart
                  title="Inscritos"
                  data={series?.subs ?? []}
                  color="#2dd4bf"
                  aggregation="last"
                />
              </div>
            </section>
          );
        })
      )}

      {/* ------------------- Para monitorar ------------------- */}
      <section className="card">
        <header style={{ marginBottom: 10 }}>
          <h3 style={{ margin: 0, fontSize: 14 }}>
            Recomendados para monitorar{" "}
            <span className="muted" style={{ fontWeight: 400, fontSize: 11 }}>
              (canais novos com VPD alto ou Canal Viral, ainda fora do monitoramento)
            </span>
          </h3>
        </header>
        {loading && toMonitor === null ? (
          <div className="muted" style={{ fontSize: 12 }}>carregando…</div>
        ) : !toMonitor || toMonitor.length === 0 ? (
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
                  <th style={{ width: 200 }}></th>
                </tr>
              </thead>
              <tbody>
                {toMonitor.map((s) => (
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
                    <td style={{ textAlign: "right" }}>{fmtInt(s.subscribers)}</td>
                    <td style={{ textAlign: "right" }}>{fmtInt(s.avg_vpd_recent)}</td>
                    <td style={{ textAlign: "right" }}>
                      {s.top_video_url ? (
                        <a href={s.top_video_url} target="_blank" rel="noreferrer">
                          {fmtInt(s.top_video_views)}
                        </a>
                      ) : (
                        fmtInt(s.top_video_views)
                      )}
                      {s.top_video_title && (
                        <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                          {s.top_video_title}
                        </div>
                      )}
                    </td>
                    <td className="muted" style={{ fontSize: 11 }}>{s.reason}</td>
                    <td>
                      <div className="row-actions">
                        <button
                          type="button"
                          className="btn-primary"
                          onClick={() => onMonitorSuggestion(s)}
                        >
                          Monitorar
                        </button>
                        <button
                          type="button"
                          className="btn-ghost danger"
                          onClick={() => onDismissSuggestion(s)}
                        >
                          Dispensar
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

      {/* ------------------- Possivelmente mortos ------------------- */}
      <section className="card">
        <header style={{ marginBottom: 10 }}>
          <h3 style={{ margin: 0, fontSize: 14 }}>
            Possivelmente mortos — sugeridos para pausar/remover{" "}
            <span className="muted" style={{ fontWeight: 400, fontSize: 11 }}>
              (sem uploads recentes, VPD baixo e sinal estagnado)
            </span>
          </h3>
        </header>
        {loading && toRemove === null ? (
          <div className="muted" style={{ fontSize: 12 }}>carregando…</div>
        ) : !toRemove || toRemove.length === 0 ? (
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
                {toRemove.map((s) => (
                  <tr key={s.channel_id}>
                    <td>
                      <a href={s.url ?? "#"} target="_blank" rel="noreferrer">
                        {s.title}
                      </a>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {s.days_since_last_upload ?? "—"}
                    </td>
                    <td style={{ textAlign: "right" }}>{fmtInt(s.avg_vpd_recent)}</td>
                    <td className="muted" style={{ fontSize: 11 }}>{s.signal ?? "—"}</td>
                    <td className="muted" style={{ fontSize: 11 }}>{s.reason}</td>
                    <td>
                      <div className="row-actions">
                        <button
                          type="button"
                          className="btn-ghost"
                          onClick={() => onPauseDead(s)}
                        >
                          Pausar
                        </button>
                        <button
                          type="button"
                          className="btn-ghost danger"
                          onClick={() => onRemoveDead(s)}
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
    </div>
  );
}
