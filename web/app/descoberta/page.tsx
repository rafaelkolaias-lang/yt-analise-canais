import { apiGet, type DiscoveryDefaults } from "@/lib/api";

import { DescobertaForm } from "./DescobertaForm";

export const dynamic = "force-dynamic";

async function loadDefaults(): Promise<
  { ok: true; data: DiscoveryDefaults } | { ok: false; error: string }
> {
  try {
    const data = await apiGet<DiscoveryDefaults>("/api/discovery/defaults");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export default async function DescobertaPage() {
  const result = await loadDefaults();

  return (
    <>
      <header className="page-header">
        <h2>Descoberta</h2>
        <p className="muted">
          Busca canais e vídeos no YouTube usando os filtros configurados. Os
          campos começam preenchidos com os defaults em{" "}
          <a href="/configuracoes">Configurações</a>. Cada linha tem ações para
          enviar o canal ou o vídeo ao monitoramento.
        </p>
      </header>

      {result.ok ? (
        <DescobertaForm defaults={result.data} />
      ) : (
        <div className="card">
          <span className="status-pill danger">API offline</span>
          <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
            Não foi possível carregar os defaults. Suba o backend com{" "}
            <code>uvicorn app.main:app --reload --port 8000</code>.
          </p>
          <p className="muted" style={{ marginTop: 6, fontSize: 11 }}>Detalhe: {result.error}</p>
        </div>
      )}
    </>
  );
}
