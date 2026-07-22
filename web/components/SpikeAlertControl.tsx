"use client";

import { useState } from "react";

import { apiPatch, type MonitoredChannel } from "@/lib/api";

/**
 * Controle do alerta de pico de views de UM canal (Monitoramento).
 *
 * Sino liga/desliga; com o alerta ligado aparece o campo do multiplicador
 * (ex.: 2 = disparar quando o ganho de views das últimas 24h for 2x a média
 * diária dos 7 dias anteriores do canal). Salva direto no PATCH
 * /api/monitoring/channels/{id}/spike-alert.
 */
export function SpikeAlertControl({ channel }: { channel: MonitoredChannel }) {
  const [enabled, setEnabled] = useState(channel.spike_alert_enabled ?? false);
  const [multiplier, setMultiplier] = useState<string>(
    String(channel.spike_alert_multiplier ?? 2)
  );
  const [saving, setSaving] = useState(false);

  async function patch(body: { enabled?: boolean; multiplier?: number }) {
    setSaving(true);
    try {
      const updated = await apiPatch<MonitoredChannel>(
        `/api/monitoring/channels/${channel.id}/spike-alert`,
        body
      );
      setEnabled(updated.spike_alert_enabled);
      setMultiplier(String(updated.spike_alert_multiplier));
    } catch {
      // Reverte visual pro estado do servidor conhecido.
      setEnabled(channel.spike_alert_enabled ?? false);
      setMultiplier(String(channel.spike_alert_multiplier ?? 2));
    } finally {
      setSaving(false);
    }
  }

  function commitMultiplier() {
    const v = Number(multiplier.replace(",", "."));
    if (!Number.isFinite(v) || v <= 1) {
      setMultiplier(String(channel.spike_alert_multiplier ?? 2));
      return;
    }
    void patch({ multiplier: v });
  }

  return (
    <span
      style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
      onClick={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        className="btn-ghost"
        disabled={saving}
        title={
          enabled
            ? `Alerta de pico LIGADO (dispara a ${multiplier}x a média). Clique para desligar.`
            : "Alerta de pico desligado. Clique para ser avisado quando o canal ganhar views muito acima da média."
        }
        aria-label={`alerta de pico do canal ${channel.title}`}
        onClick={() => void patch({ enabled: !enabled })}
        style={enabled ? {} : { opacity: 0.55 }}
      >
        {enabled ? "🔔" : "🔕"}
      </button>
      {enabled && (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
          <input
            type="number"
            min={1.1}
            step={0.5}
            value={multiplier}
            disabled={saving}
            onChange={(e) => setMultiplier(e.target.value)}
            onBlur={commitMultiplier}
            onKeyDown={(e) => {
              if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            }}
            title="Multiplicador do alerta (ex.: 2 = 2x a média do canal)"
            style={{ width: 52, fontSize: 12, padding: "2px 4px" }}
          />
          <span className="muted" style={{ fontSize: 11 }}>
            x
          </span>
        </span>
      )}
    </span>
  );
}
