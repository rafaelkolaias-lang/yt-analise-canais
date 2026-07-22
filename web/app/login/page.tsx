"use client";

import { useState } from "react";

import { API_URL, type LoginResponse } from "@/lib/api";
import { setToken } from "@/lib/authToken";

/**
 * Tela de login. Fica FORA do shell (sem sidebar/notificações — ver AppShell).
 * Usa fetch direto (não apiPost) porque um 401 aqui significa "senha errada",
 * não "sessão expirada" — não pode disparar o redirect global.
 */
export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return;
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, client: "web" }),
        cache: "no-store",
      });
      if (res.status === 401) {
        setError("Usuário ou senha inválidos.");
        return;
      }
      if (!res.ok) {
        setError(`Falha no login (HTTP ${res.status}). Tente novamente.`);
        return;
      }
      const data = (await res.json()) as LoginResponse;
      setToken(data.token);
      // Reload completo (não router.push): o middleware e as páginas SSR
      // precisam ver o cookie novo desde a primeira request.
      window.location.href = "/";
    } catch {
      setError("Não foi possível falar com a API. Verifique a conexão.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      <form
        onSubmit={onSubmit}
        className="card"
        style={{ width: "100%", maxWidth: 360 }}
      >
        <h1 style={{ fontSize: 20, marginBottom: 4 }}>RK Youtube Analyzer</h1>
        <p className="muted" style={{ fontSize: 12, marginBottom: 16 }}>
          Entre para acessar o painel.
        </p>

        <label className="muted" style={{ fontSize: 12 }}>
          Usuário
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
            style={{ width: "100%", marginTop: 4, marginBottom: 12 }}
          />
        </label>

        <label className="muted" style={{ fontSize: 12 }}>
          Senha
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            style={{ width: "100%", marginTop: 4, marginBottom: 16 }}
          />
        </label>

        {error && (
          <div className="status-pill danger" style={{ marginBottom: 12 }}>
            {error}
          </div>
        )}

        <button type="submit" disabled={loading} style={{ width: "100%" }}>
          {loading ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
