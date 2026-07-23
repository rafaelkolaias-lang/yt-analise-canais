"use client";

import { useState } from "react";

import { apiPatch, type MonitoredChannel } from "@/lib/api";

/**
 * Controles de metadados do usuário por canal (Monitoramento):
 *  - FavoriteStar: estrela liga/desliga (channels.is_favorite). Favoritos
 *    sobem pro topo da lista (ver applyChannelFilters).
 *  - ChannelNote: observação/nota livre (channels.notes) com editor inline.
 *
 * Ambos salvam via PATCH /api/monitoring/channels/{id}/meta e devolvem o
 * canal atualizado pro pai via `onChanged` (merge no estado da lista).
 */

type MetaPatch = { is_favorite?: boolean; notes?: string };

// Shape mínimo que os controles precisam — aceita MonitoredChannel
// (Monitoramento) e ChannelAnalyticsBasic (Analytics).
export type ChannelMetaShape = {
  id: number;
  title: string;
  is_favorite: boolean;
  notes: string | null;
};

async function patchMeta(
  channelId: number,
  body: MetaPatch
): Promise<MonitoredChannel> {
  return apiPatch<MonitoredChannel>(
    `/api/monitoring/channels/${channelId}/meta`,
    body
  );
}

export function FavoriteStar({
  channel,
  onChanged,
}: {
  channel: ChannelMetaShape;
  onChanged: (updated: MonitoredChannel) => void;
}) {
  const [saving, setSaving] = useState(false);
  const fav = channel.is_favorite;

  return (
    <button
      type="button"
      disabled={saving}
      title={fav ? "Remover dos favoritos" : "Marcar como favorito (sobe pro topo da lista)"}
      aria-label={`favoritar canal ${channel.title}`}
      onClick={async (e) => {
        e.stopPropagation();
        setSaving(true);
        try {
          const updated = await patchMeta(channel.id, { is_favorite: !fav });
          onChanged(updated);
        } catch {
          /* mantém estado atual */
        } finally {
          setSaving(false);
        }
      }}
      style={{
        background: "none",
        border: "none",
        cursor: "pointer",
        padding: 0,
        fontSize: 15,
        lineHeight: 1,
        color: fav ? "#f0b429" : "var(--text-dim)",
        opacity: saving ? 0.5 : 1,
      }}
    >
      {fav ? "★" : "☆"}
    </button>
  );
}

export function ChannelNote({
  channel,
  onChanged,
}: {
  channel: ChannelMetaShape;
  onChanged: (updated: MonitoredChannel) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  function openEditor(e?: React.MouseEvent) {
    e?.stopPropagation();
    setDraft(channel.notes ?? "");
    setEditing(true);
  }

  async function save() {
    setSaving(true);
    try {
      const updated = await patchMeta(channel.id, { notes: draft });
      onChanged(updated);
      setEditing(false);
    } catch {
      /* editor continua aberto pro usuário tentar de novo */
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <div style={{ marginTop: 6 }} onClick={(e) => e.stopPropagation()}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Sua observação sobre este canal…"
          rows={3}
          autoFocus
          maxLength={5000}
          style={{ width: "100%", fontSize: 12, resize: "vertical" }}
        />
        <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
          <button
            type="button"
            className="btn-primary"
            disabled={saving}
            onClick={save}
            style={{ fontSize: 11, padding: "3px 10px" }}
          >
            {saving ? "..." : "Salvar"}
          </button>
          <button
            type="button"
            className="btn-ghost"
            disabled={saving}
            onClick={() => setEditing(false)}
            style={{ fontSize: 11, padding: "3px 10px" }}
          >
            Cancelar
          </button>
        </div>
      </div>
    );
  }

  if (channel.notes) {
    return (
      <div
        className="muted"
        style={{ fontSize: 11, marginTop: 4, cursor: "pointer", whiteSpace: "pre-wrap" }}
        title="Clique para editar a observação"
        onClick={openEditor}
      >
        📝 {channel.notes}
      </div>
    );
  }

  return (
    <button
      type="button"
      className="muted"
      onClick={openEditor}
      title="Adicionar observação/lembrete sobre este canal"
      style={{
        background: "none",
        border: "none",
        cursor: "pointer",
        padding: 0,
        fontSize: 10,
        marginTop: 4,
        textAlign: "left",
        color: "var(--text-dim)",
      }}
    >
      + observação
    </button>
  );
}
