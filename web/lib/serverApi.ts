/**
 * Fetch autenticado para SERVER COMPONENTS (SSR).
 *
 * As páginas server-side não têm localStorage — o token chega pelo cookie
 * `auth_token` (gravado pelo /login). Este módulo importa `next/headers` e
 * por isso NUNCA deve ser importado por componentes client.
 */
import { cookies } from "next/headers";

import { API_URL } from "@/lib/api";

async function serverAuthHeaders(): Promise<Record<string, string>> {
  try {
    const jar = await cookies();
    const token = jar.get("auth_token")?.value;
    return token ? { Authorization: `Bearer ${decodeURIComponent(token)}` } : {};
  } catch {
    return {};
  }
}

export async function serverApiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    cache: "no-store",
    headers: await serverAuthHeaders(),
  });
  if (!res.ok) {
    throw new Error(`GET ${path} falhou: ${res.status}`);
  }
  return res.json();
}

/** Variante tolerante: retorna null em qualquer falha (padrão do dashboard). */
export async function serverApiGetOrNull<T>(path: string): Promise<T | null> {
  try {
    return await serverApiGet<T>(path);
  } catch {
    return null;
  }
}
