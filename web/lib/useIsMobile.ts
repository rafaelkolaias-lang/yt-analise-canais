"use client";

import { useEffect, useState } from "react";

/**
 * Retorna `true` quando a viewport é ≤ `maxWidth` (default 768px).
 *
 * Inicializa com `false` no SSR para garantir hidratação consistente, e
 * atualiza via `matchMedia` logo após o mount. Em telas grandes (desktop)
 * isso significa zero re-renders extras.
 */
export function useIsMobile(maxWidth: number = 768): boolean {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(`(max-width: ${maxWidth}px)`);
    const apply = () => setIsMobile(mql.matches);
    apply();
    mql.addEventListener("change", apply);
    return () => mql.removeEventListener("change", apply);
  }, [maxWidth]);

  return isMobile;
}
