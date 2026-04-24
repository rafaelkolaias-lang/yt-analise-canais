"use client";

import { useState } from "react";

import type { DiscoveryRunSummary, SyncRun } from "@/lib/api";

type Tab = "sync" | "discovery";

type Props = {
  syncRuns: SyncRun[];
  discoveryRuns: DiscoveryRunSummary[];
};

function formatDT(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function duration(start: string, end: string | null): string {
  if (!end) return "em andamento";
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  if (!Number.isFinite(s) || !Number.isFinite(e)) return "—";
  const sec = Math.max(0, Math.round((e - s) / 1000));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const rs = sec % 60;
  return `${m}m${rs}s`;
}

function StatusPill({ status }: { status: string }) {
  const cls =
    status === "success"
      ? "status-pill"
      : status === "partial" || status === "running"
      ? "status-pill warn"
      : "status-pill danger";
  return <span className={cls} style={{ fontSize: 10 }}>{status}</span>;
}

export function RunsView({ syncRuns, discoveryRuns }: Props) {
  const [tab, setTab] = useState<Tab>("sync");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="tabs">
        <button
          className={tab === "sync" ? "tab active" : "tab"}
          onClick={() => setTab("sync")}
        >
          Sync <span className="tab-count">{syncRuns.length}</span>
        </button>
        <button
          className={tab === "discovery" ? "tab active" : "tab"}
          onClick={() => setTab("discovery")}
        >
          Descoberta <span className="tab-count">{discoveryRuns.length}</span>
        </button>
      </div>

      {tab === "sync" && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>Tipo</th>
                <th>Status</th>
                <th>Iniciado</th>
                <th>Duração</th>
                <th style={{ textAlign: "right" }}>Canais</th>
                <th style={{ textAlign: "right" }}>Vídeos</th>
                <th>Observações</th>
              </tr>
            </thead>
            <tbody>
              {syncRuns.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td className="muted" style={{ fontSize: 11 }}>{r.type}</td>
                  <td><StatusPill status={r.status} /></td>
                  <td style={{ fontSize: 11 }}>{formatDT(r.started_at)}</td>
                  <td style={{ fontSize: 11 }}>{duration(r.started_at, r.finished_at)}</td>
                  <td style={{ textAlign: "right" }}>{r.channels_processed}</td>
                  <td style={{ textAlign: "right" }}>{r.videos_processed}</td>
                  <td className="muted" style={{ fontSize: 11, maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.notes ?? undefined}>
                    {r.notes ?? "—"}
                  </td>
                </tr>
              ))}
              {syncRuns.length === 0 && (
                <tr>
                  <td colSpan={8} className="muted" style={{ textAlign: "center", padding: 16 }}>
                    nenhum sync ainda. Vá ao <a href="/">Dashboard</a> e clique em Verificar agora.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === "discovery" && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>Termos</th>
                <th>Status</th>
                <th>Iniciado</th>
                <th>Duração</th>
                <th style={{ textAlign: "right" }}>Canais</th>
                <th style={{ textAlign: "right" }}>Vídeos</th>
              </tr>
            </thead>
            <tbody>
              {discoveryRuns.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td style={{ maxWidth: 380, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.terms}>
                    {r.terms}
                  </td>
                  <td><StatusPill status={r.status} /></td>
                  <td style={{ fontSize: 11 }}>{formatDT(r.started_at)}</td>
                  <td style={{ fontSize: 11 }}>{duration(r.started_at, r.finished_at)}</td>
                  <td style={{ textAlign: "right" }}>{r.channels_found}</td>
                  <td style={{ textAlign: "right" }}>{r.videos_found}</td>
                </tr>
              ))}
              {discoveryRuns.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted" style={{ textAlign: "center", padding: 16 }}>
                    nenhuma busca ainda. <a href="/descoberta">Rode uma em Descoberta</a>.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
