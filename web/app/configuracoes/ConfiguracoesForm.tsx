"use client";

import { useMemo, useState } from "react";

import { HelpTooltip } from "@/components/HelpTooltip";
import { NotificationsSettings } from "@/components/NotificationsSettings";
import { SecretInput } from "@/components/SecretInput";
import { SettingInput } from "@/components/SettingInput";
import { useToast } from "@/components/Toaster";
import { YouTubeKeysManager } from "@/components/YouTubeKeysManager";
import { apiPut, type AppSetting } from "@/lib/api";

type Subgroup = {
  id: string;
  title: string;
  description?: string;
  match: (key: string) => boolean;
};

type Section = {
  id: string;
  title: string;
  description?: string;
  match: (key: string) => boolean;
  // Quando definido, os itens da seção são divididos em subgrupos. Cada chave é
  // testada na ordem; a primeira que casar leva o item. Itens sem subgrupo caem
  // num bloco "Outros" no fim da seção.
  subgroups?: Subgroup[];
};

// A ordem desta lista define a numeração mostrada na UI (1., 2., 3., …).
// Os números 1.x, 2.x, 3.x… também aparecem no início de cada `description` e
// `help` no backend (api/app/seed.py + api/app/services/settings_help.py),
// permitindo referência cruzada nos textos do tooltip "?" (ex: "ver 4.2").
const SECTIONS: Section[] = [
  {
    id: "sync",
    title: "Sincronização",
    description: "Cadência do sync automático dos canais e vídeos monitorados.",
    match: (k) => k.startsWith("sync_"),
  },
  {
    id: "search",
    title: "Busca / Discovery",
    description: "Filtros usados na busca de canais e vídeos.",
    match: (k) => k.startsWith("search."),
  },
  {
    id: "channel",
    title: "Scoring de canal",
    description: "Limites usados para classificar canais (promissor, saturado, etc).",
    match: (k) => k.startsWith("channel."),
  },
  {
    id: "monitor",
    title: "Monitoramento",
    description: "Como o sistema acompanha os canais adicionados.",
    match: (k) => k.startsWith("monitor."),
  },
  {
    id: "analytics",
    title: "Analytics",
    description:
      "Thresholds usados para classificar o sinal dos canais (aquecendo, promissor, saturado, estável).",
    match: (k) => k.startsWith("analytics."),
  },
  {
    id: "discovery",
    title: "Descoberta automática",
    description:
      "Descoberta que roda após cada sync para encontrar novos canais sem busca manual. Os termos são editáveis (um por linha) e o sistema também gera termos derivados a partir dos canais já descobertos.",
    match: (k) => k.startsWith("discovery."),
  },
  {
    id: "suggestions",
    title: "Sugestões",
    description:
      "Thresholds das recomendações exibidas em Monitoramento → Sugestões. São RECOMENDAÇÕES — nada é executado automaticamente. Estão separadas das outras configs para evitar mistura.",
    match: (k) => k.startsWith("suggestions."),
    subgroups: [
      {
        id: "monitor-basic",
        title: "Sugerir canais para monitorar (regra simples)",
        description:
          "Canal descoberto vira sugestão se tiver VPD acima do mínimo E idade abaixo do máximo.",
        match: (k) =>
          k === "suggestions.monitor_min_vpd" ||
          k === "suggestions.monitor_max_age_days",
      },
      {
        id: "monitor-breakout",
        title: "Sugerir Canal Viral",
        description:
          "Canal pequeno e novo, com poucos vídeos, mas com um vídeo desproporcional. Todas as condições valem em conjunto (E lógico).",
        match: (k) => k.startsWith("suggestions.monitor_breakout_"),
      },
      {
        id: "dead",
        title: "Sugerir canais mortos para pausar/remover",
        description:
          "Canal monitorado sem novos uploads há muito tempo E com VPD baixo. As regras valem em conjunto (E lógico).",
        match: (k) => k.startsWith("suggestions.dead_"),
      },
    ],
  },
  {
    id: "youtube",
    title: "API do YouTube",
    description:
      "Chaves da YouTube Data API v3. A chave é cifrada no banco com Fernet (AES-128) e nunca é retornada em texto plano.",
    match: (k) => k.startsWith("youtube."),
  },
];

/**
 * Settings que existem no banco por necessidade interna (estado persistido,
 * cache, etc.) mas que o usuario nao deve ver/editar na UI. Sao filtradas
 * antes do agrupamento em SECTIONS.
 */
const INTERNAL_KEYS = new Set<string>([
  // Estado de consumo da quota do dia, escrito pelo youtube_client a cada
  // request. Reseta sozinho em UTC. Nao deve aparecer no painel.
  "youtube.quota_usage_today",
  // Lista de chaves queimadas (interno). Aparece via YouTubeKeysManager.
  "youtube.api_keys_burned",
  // youtube.api_keys agora tem UI dedicada (YouTubeKeysManager) renderizada
  // logo apos a secao de "API do YouTube". Esconder aqui evita o textarea
  // generico de SecretInput.
  "youtube.api_keys",
]);

type Props = {
  initial: AppSetting[];
};

export function ConfiguracoesForm({ initial }: Props) {
  const [settings, setSettings] = useState<AppSetting[]>(initial);
  const toast = useToast();

  async function save(key: string, value: string | null) {
    try {
      const updated = await apiPut<AppSetting>(`/api/settings/${encodeURIComponent(key)}`, {
        value,
      });
      setSettings((prev) => prev.map((s) => (s.key === key ? updated : s)));
      toast.success(`${key} salvo.`);
    } catch (e) {
      toast.error(`Falha ao salvar ${key}: ${e instanceof Error ? e.message : String(e)}`);
      throw e;
    }
  }

  const grouped = useMemo(() => {
    const visible = settings.filter((s) => !INTERNAL_KEYS.has(s.key));
    const used = new Set<string>();
    const groups = SECTIONS.map((section) => {
      const items = visible.filter((s) => section.match(s.key));
      items.forEach((i) => used.add(i.key));
      return { section, items };
    });
    const other = visible.filter((s) => !used.has(s.key));
    if (other.length > 0) {
      groups.push({
        section: {
          id: "other",
          title: "Outros",
          description: undefined,
          match: () => true,
        },
        items: other,
      });
    }
    return groups;
  }, [settings]);

  function renderRow(item: AppSetting) {
    return (
      <div key={item.key} className="settings-row">
        <div className="settings-meta">
          <div style={{ fontSize: 13, fontWeight: 500, display: "flex", alignItems: "center", flexWrap: "wrap" }}>
            <span>{item.description || item.key}</span>
            {item.help && <HelpTooltip text={item.help} />}
          </div>
          {item.description && (
            <code
              className="muted"
              style={{ fontSize: 11, marginTop: 2, display: "block" }}
            >
              {item.key}
            </code>
          )}
        </div>
        <div className="settings-control">
          {item.is_secret ? (
            <SecretInput
              hasValue={item.has_value}
              masked={item.value}
              onSave={(v) => save(item.key, v)}
              onClear={() => save(item.key, "")}
              multiline={item.key === "youtube.api_keys"}
              placeholder={
                item.key === "youtube.api_keys"
                  ? "uma chave por linha"
                  : undefined
              }
            />
          ) : (
            <SettingInput
              initialValue={item.value}
              valueType={item.value_type}
              multiline={item.key === "discovery.auto_keywords"}
              onSave={(v) => save(item.key, v)}
            />
          )}
        </div>
      </div>
    );
  }

  function renderSectionBody(
    section: Section,
    items: AppSetting[],
    sectionNumber: number,
  ) {
    if (!section.subgroups || section.subgroups.length === 0) {
      return <div className="settings-list">{items.map(renderRow)}</div>;
    }

    const claimed = new Set<string>();
    const subgroupBlocks = section.subgroups.map((sub) => {
      const subItems = items.filter((i) => sub.match(i.key));
      subItems.forEach((i) => claimed.add(i.key));
      return { sub, items: subItems };
    });
    const leftover = items.filter((i) => !claimed.has(i.key));

    let subIndex = 0;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {subgroupBlocks.map(({ sub, items: subItems }) => {
          if (subItems.length === 0) return null;
          subIndex += 1;
          const subPrefix = `${sectionNumber}.${subIndex}`;
          return (
            <div key={sub.id}>
              <div style={{ marginBottom: 8 }}>
                <h4
                  style={{
                    margin: 0,
                    fontSize: 13,
                    color: "var(--text)",
                    textTransform: "uppercase",
                    letterSpacing: 0.5,
                  }}
                >
                  {subPrefix}. {sub.title}
                </h4>
                {sub.description && (
                  <p
                    className="muted"
                    style={{ margin: "2px 0 0", fontSize: 12 }}
                  >
                    {sub.description}
                  </p>
                )}
              </div>
              <div className="settings-list">{subItems.map(renderRow)}</div>
            </div>
          );
        })}
        {leftover.length > 0 && (
          <div>
            <div style={{ marginBottom: 8 }}>
              <h4
                style={{
                  margin: 0,
                  fontSize: 13,
                  color: "var(--text)",
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                }}
              >
                Outros
              </h4>
            </div>
            <div className="settings-list">{leftover.map(renderRow)}</div>
          </div>
        )}
      </div>
    );
  }

  // Numera as secoes na ordem de exibicao (so as que tem itens). Secao "Outros"
  // (catch-all) nao recebe numero — fica fora do esquema 1.x, 2.x.
  let sectionNumber = 0;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <NotificationsSettings />
      {grouped.map(({ section, items }) => {
        if (items.length === 0) return null;
        const isCatchAll = section.id === "other";
        if (!isCatchAll) sectionNumber += 1;
        const heading = isCatchAll
          ? section.title
          : `${sectionNumber}. ${section.title}`;
        const isYouTubeSection = section.id === "youtube";
        return (
          <section key={section.id} className="card">
            <header style={{ marginBottom: 12 }}>
              <h3 style={{ margin: 0, fontSize: 15 }}>{heading}</h3>
              {section.description && (
                <p className="muted" style={{ margin: "2px 0 0", fontSize: 12 }}>
                  {section.description}
                </p>
              )}
            </header>
            {isYouTubeSection && (
              <div style={{ marginBottom: 16 }}>
                <YouTubeKeysManager />
              </div>
            )}
            {renderSectionBody(section, items, sectionNumber)}
          </section>
        );
      })}
    </div>
  );
}
