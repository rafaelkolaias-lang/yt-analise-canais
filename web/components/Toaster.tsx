"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
} from "react";

type ToastKind = "success" | "error" | "info";

type Toast = {
  id: number;
  kind: ToastKind;
  message: string;
};

type ToastContextValue = {
  push: (message: string, kind?: ToastKind, durationMs?: number) => void;
  success: (message: string, durationMs?: number) => void;
  error: (message: string, durationMs?: number) => void;
  info: (message: string, durationMs?: number) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast precisa estar dentro de <ToasterProvider>");
  }
  return ctx;
}

export function ToasterProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (message: string, kind: ToastKind = "info", durationMs = 3500) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev, { id, kind, message }]);
      if (durationMs > 0) {
        window.setTimeout(() => remove(id), durationMs);
      }
    },
    [remove]
  );

  const api: ToastContextValue = {
    push,
    success: (m, d) => push(m, "success", d),
    error: (m, d) => push(m, "error", d ?? 6000),
    info: (m, d) => push(m, "info", d),
  };

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toaster" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.kind}`}>
            <span className="toast-msg">{t.message}</span>
            <button
              type="button"
              className="toast-close"
              onClick={() => remove(t.id)}
              aria-label="fechar"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/**
 * Helper para telas que querem um handler padronizado de erro/sucesso
 * sem importar o hook diretamente em lugares muito isolados.
 */
export function useToastifyAsync() {
  const toast = useToast();
  return useCallback(
    async <T,>(
      fn: () => Promise<T>,
      opts: { success?: string; error?: string } = {}
    ): Promise<T | null> => {
      try {
        const r = await fn();
        if (opts.success) toast.success(opts.success);
        return r;
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        toast.error(opts.error ? `${opts.error}: ${msg}` : msg);
        return null;
      }
    },
    [toast]
  );
}

