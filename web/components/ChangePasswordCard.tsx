"use client";

import { useState } from "react";

import { apiPost } from "@/lib/api";

/**
 * Troca de senha do usuário logado (Configurações). Ao trocar, a API revoga
 * todas as OUTRAS sessões (inclusive a do app do Windows, que pedirá login
 * novamente na próxima vez).
 */
export function ChangePasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return;
    setMsg(null);
    if (next !== confirm) {
      setMsg({ ok: false, text: "A confirmação não confere com a nova senha." });
      return;
    }
    if (next.length < 4) {
      setMsg({ ok: false, text: "Nova senha deve ter pelo menos 4 caracteres." });
      return;
    }
    setLoading(true);
    try {
      await apiPost("/api/auth/change-password", {
        current_password: current,
        new_password: next,
      });
      setMsg({ ok: true, text: "Senha alterada. Outras sessões foram desconectadas." });
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      const text =
        err instanceof Error && err.message.includes("400")
          ? "Senha atual incorreta."
          : "Não foi possível trocar a senha. Tente novamente.";
      setMsg({ ok: false, text });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3 style={{ fontSize: 15, marginBottom: 4 }}>Conta — trocar senha</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
        Se ainda está usando a senha padrão do primeiro acesso, troque agora.
      </p>
      <form
        onSubmit={onSubmit}
        style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-end" }}
      >
        <label className="muted" style={{ fontSize: 12 }}>
          Senha atual
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password"
            required
            style={{ display: "block", marginTop: 4 }}
          />
        </label>
        <label className="muted" style={{ fontSize: 12 }}>
          Nova senha
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password"
            required
            style={{ display: "block", marginTop: 4 }}
          />
        </label>
        <label className="muted" style={{ fontSize: 12 }}>
          Confirmar nova senha
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            required
            style={{ display: "block", marginTop: 4 }}
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Salvando…" : "Trocar senha"}
        </button>
      </form>
      {msg && (
        <div
          className={msg.ok ? "status-pill" : "status-pill danger"}
          style={{ marginTop: 10 }}
        >
          {msg.text}
        </div>
      )}
    </div>
  );
}
