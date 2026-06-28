"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

export type ConfirmOptions = {
  /** Cabeçalho do modal. Default: "Confirmar". */
  title?: string;
  /** Texto principal (pode conter o nome do item afetado). */
  message: string;
  /** Rótulo do botão de confirmação. Default: "Confirmar". */
  confirmLabel?: string;
  /** Rótulo do botão de cancelar. Default: "Cancelar". */
  cancelLabel?: string;
  /** Quando true, o botão de confirmação fica vermelho (ação destrutiva). */
  danger?: boolean;
};

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn>(async () => false);

/**
 * Hook para pedir confirmação ao usuário via modal (substitui o `confirm()`
 * nativo do navegador). Uso:
 *
 *   const confirm = useConfirm();
 *   if (!(await confirm({ message: "Remover?", danger: true }))) return;
 */
export function useConfirm(): ConfirmFn {
  return useContext(ConfirmContext);
}

type PendingState = ConfirmOptions & { resolve: (v: boolean) => void };

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [pending, setPending] = useState<PendingState | null>(null);
  const confirmBtnRef = useRef<HTMLButtonElement | null>(null);

  const confirm = useCallback<ConfirmFn>((options) => {
    return new Promise<boolean>((resolve) => {
      setPending((prev) => {
        // Se já havia um modal pendente, resolve o anterior como cancelado
        // pra não deixar a Promise daquele pedido travada pra sempre.
        if (prev) prev.resolve(false);
        return { ...options, resolve };
      });
    });
  }, []);

  const close = useCallback(
    (result: boolean) => {
      setPending((prev) => {
        if (prev) prev.resolve(result);
        return null;
      });
    },
    []
  );

  // Foca o botão de confirmação ao abrir e fecha com Escape.
  useEffect(() => {
    if (!pending) return;
    confirmBtnRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(false);
      else if (e.key === "Enter") close(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending, close]);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending && (
        <div
          className="modal-overlay"
          role="presentation"
          onClick={() => close(false)}
        >
          <div
            className="modal-card"
            role="alertdialog"
            aria-modal="true"
            aria-label={pending.title ?? "Confirmar"}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="modal-title">{pending.title ?? "Confirmar"}</h3>
            <p className="modal-message">{pending.message}</p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => close(false)}
              >
                {pending.cancelLabel ?? "Cancelar"}
              </button>
              <button
                type="button"
                ref={confirmBtnRef}
                className={pending.danger ? "btn-primary danger" : "btn-primary"}
                onClick={() => close(true)}
              >
                {pending.confirmLabel ?? "Confirmar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}
