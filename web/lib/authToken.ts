"use client";

/**
 * Armazenamento do token de sessão no navegador.
 *
 * Vive em DOIS lugares, de propósito:
 *  - localStorage: fonte primária para os fetches client-side (Authorization).
 *  - cookie `auth_token` (não-httpOnly, SameSite=Lax): permite que as páginas
 *    server-side (SSR) e o middleware saibam que há sessão e façam fetch
 *    autenticado no servidor.
 */

const STORAGE_KEY = "auth.token";
export const AUTH_COOKIE = "auth_token";

// 30 dias — mesmo TTL da sessão web criada pela API.
const COOKIE_MAX_AGE_S = 30 * 24 * 60 * 60;

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, token);
  } catch {
    /* ignore */
  }
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${AUTH_COOKIE}=${encodeURIComponent(
    token
  )}; path=/; max-age=${COOKIE_MAX_AGE_S}; SameSite=Lax${secure}`;
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
  document.cookie = `${AUTH_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
}

/** Redireciona pro /login (uma vez) quando a API responde 401. */
export function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  if (window.location.pathname === "/login") return;
  clearToken();
  window.location.href = "/login";
}
