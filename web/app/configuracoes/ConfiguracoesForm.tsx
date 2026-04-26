"use client";

import { useMemo, useState } from "react";

import { NotificationsSettings } from "@/components/NotificationsSettings";
import { SecretInput } from "@/components/SecretInput";
import { SettingInput } from "@/components/SettingInput";
import { useToast } from "@/components/Toaster";
import { apiPut, type AppSetting } from "@/lib/api";

type Section = {
  id: string;
  title: string;
  description?: string;
  match: (key: string) => boolean;
};

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
    id: "youtube",
    title: "API do YouTube",
    description:
      "Chaves da YouTube Data API v3. A chave é cifrada no banco com Fernet (AES-128) e nunca é retornada em texto plano.",
    match: (k) => k.startsWith("youtube."),
  },
];

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
    const used = new Set<string>();
    const groups = SECTIONS.map((section) => {
      const items = settings.filter((s) => section.match(s.key));
      items.forEach((i) => used.add(i.key));
      return { section, items };
    });
    const other = settings.filter((s) => !used.has(s.key));
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <NotificationsSettings />
      {grouped.map(({ section, items }) =>
        items.length === 0 ? null : (
          <section key={section.id} className="card">
            <header style={{ marginBottom: 12 }}>
              <h3 style={{ margin: 0, fontSize: 15 }}>{section.title}</h3>
              {section.description && (
                <p className="muted" style={{ margin: "2px 0 0", fontSize: 12 }}>
                  {section.description}
                </p>
              )}
            </header>
            <div className="settings-list">
              {items.map((item) => (
                <div key={item.key} className="settings-row">
                  <div className="settings-meta">
                    <div style={{ fontSize: 13, fontWeight: 500 }}>
                      {item.description || item.key}
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
              ))}
            </div>
          </section>
        )
      )}
    </div>
  );
}
