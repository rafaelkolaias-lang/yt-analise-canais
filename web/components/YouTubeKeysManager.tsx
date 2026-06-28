"use client";

import { useEffect, useState } from "react";

import { useConfirm } from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toaster";
import {
  apiDeleteJSON,
  apiGet,
  apiPost,
  type YouTubeKeyAddResponse,
  type YouTubeKeyEntry,
  type YouTubeKeyOpResponse,
  type YouTubeKeyStatus,
} from "@/lib/api";

const STATUS_COLOR: Record<YouTubeKeyStatus, string> = {
  ok: "var(--success)",
  quota_exhausted: "var(--warn)",
  burned: "var(--danger)",
};

const STATUS_LABEL: Record<YouTubeKeyStatus, string> = {
  ok: "Ativa",
  quota_exhausted: "Quota esgotada hoje",
  burned: "Inválida (queimada)",
};

function pct(used: number, total: number): string {
  if (total <= 0) return "—";
  return `${Math.min(100, Math.round((used / total) * 100))}%`;
}

function formatDT(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function YouTubeKeysManager() {
  const [items, setItems] = useState<YouTubeKeyEntry[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const confirm = useConfirm();

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const list = await apiGet<YouTubeKeyEntry[]>("/api/youtube/keys");
      setItems(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleAdd() {
    if (!newKey.trim() || busy) return;
    setBusy(true);
    try {
      const resp = await apiPost<YouTubeKeyAddResponse>("/api/youtube/keys", {
        key: newKey.trim(),
      });
      toast.success(
        resp.created
          ? "Chave adicionada."
          : "Essa chave já estava cadastrada (sem alterações).",
      );
      setNewKey("");
      setAdding(false);
      await refresh();
    } catch (e) {
      toast.error(`Falha ao adicionar: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(fp: string, masked: string) {
    if (busy) return;
    if (
      !(await confirm({
        title: "Remover chave",
        message: `Remover a chave ${masked}? Os serviços que dependem dela vão ficar sem essa chave.`,
        confirmLabel: "Remover",
        danger: true,
      }))
    ) {
      return;
    }
    setBusy(true);
    try {
      const resp = await apiDeleteJSON<YouTubeKeyOpResponse>(
        `/api/youtube/keys/${encodeURIComponent(fp)}`,
      );
      toast.success(resp.changed ? "Chave removida." : "Chave não encontrada (já tinha sido removida).");
      await refresh();
    } catch (e) {
      toast.error(`Falha ao remover: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleUnburn(fp: string) {
    if (busy) return;
    setBusy(true);
    try {
      await apiPost<YouTubeKeyOpResponse>(
        `/api/youtube/keys/${encodeURIComponent(fp)}/unburn`,
        {},
      );
      toast.success("Chave reativada. Será testada na próxima request.");
      await refresh();
    } catch (e) {
      toast.error(`Falha ao reativar: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
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
          Chaves cadastradas
        </h4>
        <p className="muted" style={{ margin: "2px 0 0", fontSize: 12 }}>
          O sistema rotaciona entre as chaves automaticamente. Verde = ativa, amarelo = quota do dia esgotada (volta automaticamente em UTC), vermelho = inválida (precisa corrigir no console do Google).
        </p>
      </div>

      {loading && items === null ? (
        <div className="muted" style={{ fontSize: 12, padding: 8 }}>carregando…</div>
      ) : error ? (
        <div style={{ fontSize: 12, color: "var(--danger)", padding: 8 }}>
          {error}
        </div>
      ) : !items || items.length === 0 ? (
        <div className="muted" style={{ fontSize: 12, padding: 8 }}>
          Nenhuma chave cadastrada. Adicione a primeira para o sistema começar a chamar a YouTube API.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {items.map((it) => (
            <div
              key={it.fingerprint}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "8px 10px",
                borderRadius: 6,
                border: "1px solid var(--border)",
                background: "var(--bg)",
                flexWrap: "wrap",
              }}
            >
              <span
                aria-hidden
                title={STATUS_LABEL[it.status]}
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  background: STATUS_COLOR[it.status],
                  flex: "0 0 auto",
                }}
              />
              <code
                style={{
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                  fontSize: 12,
                  minWidth: 140,
                }}
              >
                {it.masked}
              </code>
              <span
                className="muted"
                style={{ fontSize: 11, minWidth: 130 }}
              >
                {STATUS_LABEL[it.status]}
              </span>
              <span
                className="muted"
                style={{ fontSize: 11, minWidth: 140 }}
              >
                {it.used_today.toLocaleString("pt-BR")} / {it.daily_quota.toLocaleString("pt-BR")} units ({pct(it.used_today, it.daily_quota)})
              </span>
              {it.status === "burned" && (
                <span
                  className="muted"
                  style={{ fontSize: 11, color: "var(--danger)", flex: "1 1 200px" }}
                >
                  {it.burned_reason ?? "inválida"} · {formatDT(it.burned_at)}
                </span>
              )}
              <div style={{ display: "flex", gap: 6, marginLeft: "auto" }}>
                {it.status === "burned" && (
                  <button
                    type="button"
                    className="btn-ghost"
                    disabled={busy}
                    onClick={() => handleUnburn(it.fingerprint)}
                  >
                    Reativar
                  </button>
                )}
                <button
                  type="button"
                  className="btn-ghost danger"
                  disabled={busy}
                  onClick={() => handleRemove(it.fingerprint, it.masked)}
                >
                  Remover
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 12 }}>
        {!adding ? (
          <button
            type="button"
            className="btn-primary"
            disabled={busy}
            onClick={() => {
              setAdding(true);
              setNewKey("");
            }}
          >
            + Adicionar chave
          </button>
        ) : (
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <input
              type="password"
              className="input"
              autoFocus
              value={newKey}
              disabled={busy}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="cole a chave aqui"
              style={{ flex: "1 1 280px", minWidth: 240 }}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleAdd();
                if (e.key === "Escape") {
                  setAdding(false);
                  setNewKey("");
                }
              }}
            />
            <button
              type="button"
              className="btn-primary"
              disabled={busy || newKey.trim().length === 0}
              onClick={() => void handleAdd()}
            >
              {busy ? "Salvando…" : "Salvar"}
            </button>
            <button
              type="button"
              className="btn-ghost"
              disabled={busy}
              onClick={() => {
                setAdding(false);
                setNewKey("");
              }}
            >
              Cancelar
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
