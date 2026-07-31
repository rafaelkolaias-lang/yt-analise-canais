import { VideosByChannelView } from "@/components/VideosByChannelView";

export const dynamic = "force-dynamic";

/**
 * Analytics → Vídeos por canal. Antes era uma aba dentro de /analytics; virou
 * rota própria pra o menu lateral poder linkar direto (item retrátil
 * "Analytics" → "Canais" / "Vídeos por canal").
 */
export default function AnalyticsVideosPage() {
  return (
    <>
      <header className="page-header">
        <h2>Vídeos por canal</h2>
        <p className="muted">
          Todos os vídeos monitorados agrupados por canal, com as séries de VPD
          e views de cada um. Use "recolher" no cabeçalho do canal para fechar o
          grupo inteiro.
        </p>
      </header>
      <VideosByChannelView />
    </>
  );
}
