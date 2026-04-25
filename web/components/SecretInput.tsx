"use client";

import { useState } from "react";

type Props = {
  hasValue: boolean;
  masked: string | null;
  disabled?: boolean;
  onSave: (newValue: string) => Promise<void>;
  onClear: () => Promise<void>;
  placeholder?: string;
  /**
   * Quando true, o campo de edição vira um textarea (várias linhas). Útil
   * pra valores que comportam múltiplos itens — ex.: várias YouTube API keys,
   * uma por linha. O backend aceita tanto `,` quanto `\n` como separador.
   */
  multiline?: boolean;
};

export function SecretInput({
  hasValue,
  masked,
  disabled,
  onSave,
  onClear,
  placeholder = "cole o valor aqui",
  multiline = false,
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

  const editor = multiline ? (
    <textarea
      className="input"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      placeholder={placeholder}
      autoFocus
      rows={5}
      style={{
        flex: "1 1 100%",
        minWidth: 280,
        fontFamily:
          'ui-monospace, SFMono-Regular, Menlo, Monaco, "Courier New", monospace',
        fontSize: 12,
        resize: "vertical",
      }}
    />
  ) : (
    <input
      type="password"
      className="input"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      placeholder={placeholder}
      autoFocus
      style={{ flex: "1 1 260px", minWidth: 240 }}
    />
  );

  return (
    <div
      style={{
        display: "flex",
        alignItems: multiline ? "flex-start" : "center",
        gap: 8,
        flexWrap: "wrap",
        width: multiline ? "100%" : undefined,
      }}
    >
      {editor}
      <div style={{ display: "flex", gap: 8 }}>
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
    </div>
  );
}
