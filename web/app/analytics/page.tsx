import {
  API_URL,
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
  // O overview agora é buscado no client porque depende do filtro de status.
  const niches = await fetchJSON<NicheRow[]>("/api/analytics/niches");

  return (
    <>
      <header className="page-header">
        <h2>Analytics</h2>
        <p className="muted">
          Sinais de aceleração, gráficos por canal e agregação por nicho. Dados
          vêm dos snapshots coletados automaticamente pelo sync.
        </p>
      </header>
      <AnalyticsView niches={niches ?? []} />
    </>
  );
}
