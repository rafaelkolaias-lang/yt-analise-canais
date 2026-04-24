"use client";

import { useState } from "react";

type Props = {
  hasValue: boolean;
  masked: string | null;
  disabled?: boolean;
  onSave: (newValue: string) => Promise<void>;
  onClear: () => Promise<void>;
  placeholder?: string;
};

export function SecretInput({
  hasValue,
  masked,
  disabled,
  onSave,
  onClear,
  placeholder = "cole o valor aqui",
}: Props) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  if (!editing) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <code className="secret-display">
          {hasValue ? masked ?? "********" : <span className="muted">não configurado</span>}
        </code>
        <button
          type="button"
          className="btn-ghost"
          disabled={disabled}
          onClick={() => {
            setValue("");
            setEditing(true);
          }}
        >
          {hasValue ? "Alterar" : "Configurar"}
        </button>
        {hasValue && (
          <button
            type="button"
            className="btn-ghost danger"
            disabled={disabled || busy}
            onClick={async () => {
              if (!confirm("Remover esta chave? Os serviços que dependem dela vão parar de funcionar.")) return;
              setBusy(true);
              try {
                await onClear();
              } finally {
                setBusy(false);
              }
            }}
          >
            Remover
          </button>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <input
        type="password"
        className="input"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        autoFocus
        style={{ flex: "1 1 260px", minWidth: 240 }}
      />
      <button
        type="button"
        className="btn-primary"
        disabled={busy || value.length === 0}
        onClick={async () => {
          setBusy(true);
          try {
            await onSave(value);
            setEditing(false);
            setValue("");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Salvando..." : "Salvar"}
      </button>
      <button
        type="button"
        className="btn-ghost"
        disabled={busy}
        onClick={() => {
          setEditing(false);
          setValue("");
        }}
      >
        Cancelar
      </button>
    </div>
  );
}
