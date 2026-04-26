"use client";

import { useState } from "react";

type Props = {
  initialValue: string | null;
  valueType: string;
  disabled?: boolean;
  /** Renderiza textarea de várias linhas em vez de input. */
  multiline?: boolean;
  onSave: (newValue: string) => Promise<void>;
};

export function SettingInput({
  initialValue,
  valueType,
  disabled,
  multiline = false,
  onSave,
}: Props) {
  const [value, setValue] = useState(initialValue ?? "");
  const [busy, setBusy] = useState(false);

  const dirty = value !== (initialValue ?? "");
  const inputType =
    valueType === "int" || valueType === "float" ? "number" : "text";

  return (
    <div
      style={{
        display: "flex",
        alignItems: multiline ? "flex-start" : "center",
        gap: 8,
        flex: 1,
      }}
    >
      {multiline ? (
        <textarea
          className="input"
          value={value}
          disabled={disabled || busy}
          onChange={(e) => setValue(e.target.value)}
          rows={6}
          style={{
            flex: "1 1 220px",
            minWidth: 160,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontSize: 12,
          }}
        />
      ) : (
        <input
          type={inputType}
          className="input"
          value={value}
          disabled={disabled || busy}
          onChange={(e) => setValue(e.target.value)}
          style={{ flex: "1 1 220px", minWidth: 160 }}
        />
      )}
      <button
        type="button"
        className="btn-primary"
        disabled={!dirty || busy}
        onClick={async () => {
          setBusy(true);
          try {
            await onSave(value);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "..." : "Salvar"}
      </button>
    </div>
  );
}
