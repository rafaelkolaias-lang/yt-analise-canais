import { SugestoesView } from "./SugestoesView";

export const dynamic = "force-dynamic";

export default function SugestoesPage() {
  return (
    <>
      <header className="page-header">
        <h2>Sugestões</h2>
        <p className="muted">
          Recomendações do sistema: canais descobertos que valem monitorar, os
          que estão <strong>em observação automática</strong> (o sistema
          acompanha a evolução por você) e monitorados que parecem mortos. Nada
          é executado sem sua decisão. Thresholds em{" "}
          <a href="/configuracoes">Configurações → Sugestões</a>.
        </p>
      </header>
      <SugestoesView />
    </>
  );
}
