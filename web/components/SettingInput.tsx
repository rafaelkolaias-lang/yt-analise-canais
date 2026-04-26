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

function parseBool(raw: string | null): boolean {
  if (!raw) return false;
  return ["1", "true", "yes", "on"].includes(raw.trim().toLowerCase());
}

export function SettingInput(props: Props) {
  if (props.valueType === "bool") {
    return (
      <BoolToggleInput
        initialValue={props.initialValue}
        disabled={props.disabled}
        onSave={props.onSave}
      />
    );
  }
  return <TextSettingInput {...props} />;
}

function TextSettingInput({
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

function BoolToggleInput({
  initialValue,
  disabled,
  onSave,
}: {
  initialValue: string | null;
  disabled?: boolean;
  onSave: (newValue: string) => Promise<void>;
}) {
  const [enabled, setEnabled] = useState(parseBool(initialValue));
  const [busy, setBusy] = useState(false);

  async function toggle() {
    if (busy || disabled) return;
    const next = !enabled;
    setEnabled(next);
    setBusy(true);
    try {
      await onSave(next ? "true" : "false");
    } catch {
      setEnabled(!next);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        flex: 1,
      }}
    >
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-busy={busy}
        disabled={disabled || busy}
        onClick={toggle}
        title={enabled ? "Ligado — clique para desligar" : "Desligado — clique para ligar"}
        style={{
          position: "relative",
          width: 46,
          height: 26,
          borderRadius: 999,
          border: "1px solid var(--border)",
          background: enabled ? "var(--accent)" : "var(--bg)",
          cursor: disabled || busy ? "not-allowed" : "pointer",
          padding: 0,
          transition: "background 0.15s",
          opacity: disabled ? 0.5 : 1,
        }}
      >
        <span
          aria-hidden
          style={{
            position: "absolute",
            top: 2,
            left: enabled ? 22 : 2,
            width: 20,
            height: 20,
            borderRadius: "50%",
            background: "#fff",
            transition: "left 0.15s",
            boxShadow: "0 1px 2px rgba(0,0,0,0.4)",
          }}
        />
      </button>
      <span
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: enabled ? "var(--success)" : "var(--text-dim)",
          minWidth: 64,
        }}
      >
        {busy ? "Salvando…" : enabled ? "Ligado" : "Desligado"}
      </span>
    </div>
  );
}
