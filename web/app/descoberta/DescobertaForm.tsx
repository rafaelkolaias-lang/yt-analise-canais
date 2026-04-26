"use client";

import { useState } from "react";

import { ChannelAvatar } from "@/components/ChannelAvatar";
import { useToast } from "@/components/Toaster";
import { VideoThumbnail } from "@/components/VideoThumbnail";
import {
  apiPost,
  type DiscoveryDefaults,
  type DiscoveryRun,
  type DiscoverySearchRequest,
  type MonitoredChannel,
  type MonitoredVideo,
  type ResultChannel,
  type ResultVideo,
} from "@/lib/api";

type Props = { defaults: DiscoveryDefaults };

type AddState = Record<string, "idle" | "loading" | "done" | "error">;

function formatInt(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("pt-BR");
}

function formatDuration(s: number | null | undefined): string {
  if (!s) return "—";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
}

export function DescobertaForm({ defaults }: Props) {
  const [termsRaw, setTermsRaw] = useState("");
  const [windowDays, setWindowDays] = useState(defaults.window_days);
  const [minViews, setMinViews] = useState(defaults.min_views);
  const [minVpd, setMinVpd] = useState(defaults.min_vpd);
  const [minDuration, setMinDuration] = useState(defaults.min_duration_seconds);
  const [languages, setLanguages] = useState(defaults.languages.join(", "));
  const [pagesPerTerm, setPagesPerTerm] = useState(defaults.pages_per_term);

  const [loading, setLoading] = useState(false);
  const [run, setRun] = useState<DiscoveryRun | null>(null);
  const [addState, setAddState] = useState<AddState>({});
  const toast = useToast();

  async function onSearch(e: React.FormEvent) {
    e.preventDefault();
    const terms = termsRaw
      .split(/[\n,]/)
      .map((t) => t.trim())
      .filter(Boolean);
    if (terms.length === 0) {
      toast.error("Informe pelo menos um termo.");
      return;
    }
    const langs = languages
      .split(",")
      .map((l) => l.trim())
      .filter(Boolean);

    const req: DiscoverySearchRequest = {
      terms,
      window_days: windowDays,
      min_views: minViews,
      min_vpd: minVpd,
      min_duration_seconds: minDuration,
      languages: langs,
      pages_per_term: pagesPerTerm,
    };

    setLoading(true);
    setRun(null);
    try {
      const result = await apiPost<DiscoveryRun>("/api/discovery/search", req);
      setRun(result);
      setAddState({});
      toast.success(
        `Busca concluída: ${result.channels_found} canais, ${result.videos_found} vídeos.`
      );
    } catch (err) {
      toast.error(`Falha na busca: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoading(false);
    }
  }

  async function onAddChannel(c: ResultChannel) {
    const k = `ch:${c.youtube_channel_id}`;
    setAddState((s) => ({ ...s, [k]: "loading" }));
    try {
      await apiPost<MonitoredChannel>("/api/monitoring/channels", {
        youtube_channel_id: c.youtube_channel_id,
      });
      setAddState((s) => ({ ...s, [k]: "done" }));
      toast.success(`Monitorando "${c.title}".`);
    } catch (e) {
      setAddState((s) => ({ ...s, [k]: "error" }));
      toast.error(e instanceof Error ? e.message : String(e));
    }
  }

  async function onAddVideo(v: ResultVideo) {
    const k = `vd:${v.youtube_video_id}`;
    setAddState((s) => ({ ...s, [k]: "loading" }));
    try {
      await apiPost<MonitoredVideo>("/api/monitoring/videos", {
        youtube_video_id: v.youtube_video_id,
      });
      setAddState((s) => ({ ...s, [k]: "done" }));
      toast.success("Vídeo adicionado ao monitoramento.");
    } catch (e) {
      setAddState((s) => ({ ...s, [k]: "error" }));
      toast.error(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div className="card" style={{ background: "rgba(79, 140, 255, 0.05)" }}>
        <div style={{ fontSize: 13 }}>
          <strong>Descoberta automática ativa.</strong>{" "}
          <span className="muted">
            Após cada sync, o sistema busca novos canais usando uma lista de
            termos seed e termos derivados dos canais já descobertos. Veja o
            histórico em{" "}
            <a href="/runs">Runs → Descoberta</a> e ajuste os termos em{" "}
            <a href="/configuracoes">Configurações → Descoberta automática</a>.
            Canais que você remover entram numa blacklist e não voltam.
          </span>
        </div>
      </div>

      <form onSubmit={onSearch} className="card">
        <header style={{ marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 15 }}>Filtros</h3>
          <p className="muted" style={{ margin: "2px 0 0", fontSize: 12 }}>
            Separe múltiplos termos por vírgula ou quebra de linha.
          </p>
        </header>

        <div className="form-grid">
          <label className="form-field" style={{ gridColumn: "1 / -1" }}>
            <span>Termos</span>
            <textarea
              className="input"
              rows={2}
              placeholder="ex: story time, podcast cortes, viral"
              value={termsRaw}
              onChange={(e) => setTermsRaw(e.target.value)}
              disabled={loading}
            />
          </label>

          <label className="form-field">
            <span>Janela (dias)</span>
            <input
              type="number"
              className="input"
              value={windowDays}
              onChange={(e) => setWindowDays(Number(e.target.value))}
              disabled={loading}
            />
          </label>

          <label className="form-field">
            <span>Views mínimas</span>
            <input
              type="number"
              className="input"
              value={minViews}
              onChange={(e) => setMinViews(Number(e.target.value))}
              disabled={loading}
            />
          </label>

          <label className="form-field">
            <span>VPD mínimo</span>
            <input
              type="number"
              className="input"
              value={minVpd}
              onChange={(e) => setMinVpd(Number(e.target.value))}
              disabled={loading}
            />
          </label>

          <label className="form-field">
            <span>Duração mín. (s)</span>
            <input
              type="number"
              className="input"
              value={minDuration}
              onChange={(e) => setMinDuration(Number(e.target.value))}
              disabled={loading}
            />
          </label>

          <label className="form-field">
            <span>Idiomas (CSV)</span>
            <input
              type="text"
              className="input"
              value={languages}
              onChange={(e) => setLanguages(e.target.value)}
              disabled={loading}
            />
          </label>

          <label className="form-field">
            <span>Páginas por termo</span>
            <input
              type="number"
              className="input"
              value={pagesPerTerm}
              onChange={(e) => setPagesPerTerm(Number(e.target.value))}
              disabled={loading}
            />
          </label>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 14 }}>
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <span className="spinner" aria-hidden />
                Buscando…
              </span>
            ) : (
              "Buscar no YouTube"
            )}
          </button>
          {loading && (
            <span className="muted" style={{ fontSize: 12 }}>
              isso chama a YouTube Data API — pode levar alguns segundos
            </span>
          )}
        </div>
      </form>

      {run && (
        <section className="card">
          <header style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <h3 style={{ margin: 0, fontSize: 15 }}>
              Resultado{" "}
              <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>
                (run #{run.id} · {run.status})
              </span>
            </h3>
            <span className="muted" style={{ fontSize: 12 }}>
              {run.channels_found} canais · {run.videos_found} vídeos
            </span>
          </header>

          <h4 style={{ margin: "8px 0 6px", fontSize: 13 }}>Vídeos</h4>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: "46%" }}>Título</th>
                  <th style={{ textAlign: "right" }}>Views</th>
                  <th style={{ textAlign: "right" }}>VPD</th>
                  <th style={{ textAlign: "right" }}>Duração</th>
                  <th>Termo</th>
                  <th style={{ width: 120 }}></th>
                </tr>
              </thead>
              <tbody>
                {run.video_results.map((v) => {
                  const state = addState[`vd:${v.youtube_video_id}`] ?? "idle";
                  return (
                    <tr key={v.id}>
                      <td>
                        <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                          <VideoThumbnail url={v.thumbnail_url} title={v.title} width={160} />
                          <div style={{ minWidth: 0 }}>
                            <a href={v.url ?? "#"} target="_blank" rel="noreferrer">
                              {v.title}
                            </a>
                            {v.youtube_channel_id && (
                              <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
                                canal {v.youtube_channel_id}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td style={{ textAlign: "right" }}>{formatInt(v.views)}</td>
                      <td style={{ textAlign: "right" }}>{formatInt(v.vpd ? Math.round(v.vpd) : null)}</td>
                      <td style={{ textAlign: "right" }}>{formatDuration(v.duration_seconds)}</td>
                      <td className="muted" style={{ fontSize: 11 }}>{v.matched_term ?? "—"}</td>
                      <td>
                        <button
                          type="button"
                          className="btn-ghost"
                          disabled={state === "loading" || state === "done"}
                          onClick={() => onAddVideo(v)}
                        >
                          {state === "done"
                            ? "✓ monitorando"
                            : state === "loading"
                            ? "..."
                            : state === "error"
                            ? "erro, tentar"
                            : "Monitorar"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {run.video_results.length === 0 && (
                  <tr>
                    <td colSpan={6} className="muted" style={{ textAlign: "center", padding: 16 }}>
                      nenhum vídeo passou nos filtros
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <h4 style={{ margin: "20px 0 6px", fontSize: 13 }}>Canais</h4>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Canal</th>
                  <th style={{ textAlign: "right" }}>Inscritos</th>
                  <th style={{ textAlign: "right" }}>Vídeos</th>
                  <th style={{ textAlign: "right" }}>Views totais</th>
                  <th style={{ width: 120 }}></th>
                </tr>
              </thead>
              <tbody>
                {run.channel_results.map((c) => {
                  const state = addState[`ch:${c.youtube_channel_id}`] ?? "idle";
                  return (
                    <tr key={c.id}>
                      <td>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <ChannelAvatar url={c.thumbnail_url} title={c.title} size={36} />
                          <a href={c.url ?? "#"} target="_blank" rel="noreferrer">
                            {c.title}
                          </a>
                        </div>
                      </td>
                      <td style={{ textAlign: "right" }}>{formatInt(c.subscribers)}</td>
                      <td style={{ textAlign: "right" }}>{formatInt(c.video_count)}</td>
                      <td style={{ textAlign: "right" }}>{formatInt(c.views_total)}</td>
                      <td>
                        <button
                          type="button"
                          className="btn-ghost"
                          disabled={state === "loading" || state === "done"}
                          onClick={() => onAddChannel(c)}
                        >
                          {state === "done"
                            ? "✓ monitorando"
                            : state === "loading"
                            ? "..."
                            : state === "error"
                            ? "erro, tentar"
                            : "Monitorar"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {run.channel_results.length === 0 && (
                  <tr>
                    <td colSpan={5} className="muted" style={{ textAlign: "center", padding: 16 }}>
                      nenhum canal correspondente
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
