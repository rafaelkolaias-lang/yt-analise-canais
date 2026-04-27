"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  /** Texto longo (didático). Quebras de linha `\n` são preservadas. */
  text: string;
  /** Rótulo curto pra acessibilidade. Default: "Mais informações". */
  label?: string;
};

/**
 * Tooltip "?" que aparece no hover (desktop) e fica preso no clique (mobile).
 * Fecha com clique fora ou tecla Esc. Texto longo respeita quebras (pre-line).
 */
export function HelpTooltip({ text, label = "Mais informações" }: Props) {
  const [open, setOpen] = useState(false);
  const [hovered, setHovered] = useState(false);
  const containerRef = useRef<HTMLSpanElement>(null);

  const visible = open || hovered;

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <span
      ref={containerRef}
      style={{ position: "relative", display: "inline-flex", marginLeft: 6 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        type="button"
        aria-label={label}
        aria-expanded={visible}
        onClick={() => setOpen((v) => !v)}
        onFocus={() => setHovered(true)}
        onBlur={() => setHovered(false)}
        style={{
          width: 18,
          height: 18,
          borderRadius: "50%",
          border: "1px solid var(--border)",
          background: "var(--bg)",
          color: "var(--text-dim)",
          fontSize: 11,
          fontWeight: 700,
          lineHeight: "16px",
          cursor: "help",
          padding: 0,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        ?
      </button>
      {visible && (
        <div
          role="tooltip"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            zIndex: 50,
            width: "min(420px, 80vw)",
            padding: "10px 12px",
            background: "var(--bg-elev)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            boxShadow: "0 6px 20px rgba(0,0,0,0.45)",
            color: "var(--text)",
            fontSize: 12,
            lineHeight: 1.5,
            whiteSpace: "pre-line",
            fontWeight: 400,
          }}
        >
          {text}
        </div>
      )}
    </span>
  );
}
