import {
  apiGet,
  type DiscoveryRunSummary,
  type SyncRun,
} from "@/lib/api";

import { RunsView } from "./RunsView";

export const dynamic = "force-dynamic";

async function loadAll(): Promise<
  | { ok: true; syncRuns: SyncRun[]; discoveryRuns: DiscoveryRunSummary[] }
  | { ok: false; error: string }
> {
  try {
    const [syncRuns, discoveryRuns] = await Promise.all([
      apiGet<SyncRun[]>("/api/sync/runs"),
      apiGet<DiscoveryRunSummary[]>("/api/discovery/runs"),
    ]);
    return { ok: true, syncRuns, discoveryRuns };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export default async function RunsPage() {
  const result = await loadAll();

  return (
    <>
      <header className="page-header">
        <h2>Runs</h2>
        <p className="muted">
          Histórico de execuções de sincronização (automáticas e manuais) e
          buscas na Descoberta.
        </p>
      </header>

      {result.ok ? (
        <RunsView syncRuns={result.syncRuns} discoveryRuns={result.discoveryRuns} />
      ) : (
        <div className="card">
          <span className="status-pill danger">API offline</span>
          <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>Detalhe: {result.error}</p>
        </div>
      )}
    </>
  );
}
