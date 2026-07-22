import { type AppSetting } from "@/lib/api";
import { serverApiGet } from "@/lib/serverApi";

import { ChangePasswordCard } from "@/components/ChangePasswordCard";
import { ConfiguracoesForm } from "./ConfiguracoesForm";

export const dynamic = "force-dynamic";

async function loadSettings(): Promise<
  { ok: true; data: AppSetting[] } | { ok: false; error: string }
> {
  try {
    const data = await serverApiGet<AppSetting[]>("/api/settings");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export default async function ConfiguracoesPage() {
  const result = await loadSettings();

  return (
    <>
      <header className="page-header">
        <h2>Configurações</h2>
        <p className="muted">
          Parâmetros de busca, scoring, monitoramento e chaves da API do YouTube.
          Alterações são salvas imediatamente. Chaves marcadas como secret são
          cifradas no banco e nunca retornam em texto plano.
        </p>
      </header>

      <ChangePasswordCard />

      {result.ok ? (
        <ConfiguracoesForm initial={result.data} />
      ) : (
        <div className="card">
          <span className="status-pill danger">API offline</span>
          <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
            Não foi possível carregar as configurações. Suba o backend com{" "}
            <code>uvicorn app.main:app --reload --port 8000</code>.
          </p>
          <p className="muted" style={{ marginTop: 6, fontSize: 11 }}>
            Detalhe: {result.error}
          </p>
        </div>
      )}
    </>
  );
}
