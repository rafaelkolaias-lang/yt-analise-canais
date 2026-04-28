"use client";

import { useCallback, useEffect, useState } from "react";

import { apiGet, type QuotaSummary } from "@/lib/api";

const POLL_MS = 30_000;

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR");
}

/**
 * Widget compacto de cota da YouTube API, fixado na sidebar esquerda.
 *
 * Diferença pra notificação: cota é ESTADO, não evento. Vive no shell
 * pra estar visível em qualquer página, com botão de refresh manual.
 */
export function QuotaSidebarWidget() {
  const [data, setData] = useState<QuotaSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiGet<QuotaSummary>("/api/notifications/quota-summary");
      setData(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  if (error && !data) {
    return (
      <div className="quota-widget">
        <div className="quota-widget-header">
          <span>Cota YouTube</span>
          <button
            type="button"
            className="quota-widget-refresh"
            onClick={refresh}
            disabled={loading}
            aria-label="recarregar cota"
            title="Recarregar"
          >
            ⟳
          </button>
        </div>
        <div className="quota-widget-error">
          falha ao carregar
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="quota-widget">
        <div className="quota-widget-header">
          <span>Cota YouTube</span>
        </div>
        <div className="quota-widget-loading">carregando…</div>
      </div>
    );
  }

  const noKeys = data.keys_count === 0;
  const pct = data.total_quota > 0 ? (data.used / data.total_quota) * 100 : 0;
  const barColor =
    pct >= 90 ? "var(--danger)" : pct >= 70 ? "var(--warn)" : "var(--success)";

  return (
    <div className="quota-widget">
      <div className="quota-widget-header">
        <span>Cota YouTube</span>
        <button
          type="button"
          className="quota-widget-refresh"
          onClick={refresh}
          disabled={loading}
          aria-label="recarregar cota"
          title="Recarregar"
        >
          {loading ? "…" : "⟳"}
        </button>
      </div>
      {noKeys ? (
        <div className="quota-widget-empty">
          Sem chave cadastrada.{" "}
          <a href="/configuracoes">Configurar</a>
        </div>
      ) : (
        <>
          <div className="quota-widget-bar">
            <div
              className="quota-widget-bar-fill"
              style={{
                width: `${Math.min(pct, 100)}%`,
                background: barColor,
              }}
            />
          </div>
          <div className="quota-widget-numbers">
            <span>
              <strong>{fmt(data.used)}</strong>/{fmt(data.total_quota)}
            </span>
            <span className="quota-widget-pct">{pct.toFixed(0)}%</span>
          </div>
          <div className="quota-widget-foot">
            {data.keys_count} {data.keys_count === 1 ? "chave" : "chaves"} · reset UTC
          </div>
        </>
      )}
    </div>
  );
}
