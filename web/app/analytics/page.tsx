import {
  API_URL,
  type AnalyticsOverview,
  type MonitoredChannel,
  type NicheRow,
} from "@/lib/api";

import { AnalyticsView } from "./AnalyticsView";

export const dynamic = "force-dynamic";

async function fetchJSON<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export default async function AnalyticsPage() {
  const [overview, channels, niches] = await Promise.all([
    fetchJSON<AnalyticsOverview>("/api/analytics/overview"),
    fetchJSON<MonitoredChannel[]>("/api/monitoring/channels"),
    fetchJSON<NicheRow[]>("/api/analytics/niches"),
  ]);

  return (
    <>
      <header className="page-header">
        <h2>Analytics</h2>
        <p className="muted">
          Sinais de aceleração, gráficos por canal e agregação por nicho. Dados
          vêm dos snapshots coletados automaticamente pelo sync.
        </p>
      </header>
      <AnalyticsView
        overview={overview}
        channels={channels ?? []}
        niches={niches ?? []}
      />
    </>
  );
}
