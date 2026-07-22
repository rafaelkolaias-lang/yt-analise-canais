import { type NicheRow } from "@/lib/api";
import { serverApiGetOrNull } from "@/lib/serverApi";

import { AnalyticsView } from "./AnalyticsView";

export const dynamic = "force-dynamic";

export default async function AnalyticsPage() {
  // O overview agora é buscado no client porque depende do filtro de status.
  const niches = await serverApiGetOrNull<NicheRow[]>("/api/analytics/niches");

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
