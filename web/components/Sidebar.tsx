"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const items = [
  { href: "/", label: "Dashboard" },
  { href: "/descoberta", label: "Descoberta" },
  { href: "/monitoramento", label: "Monitoramento" },
  { href: "/analytics", label: "Analytics" },
  { href: "/runs", label: "Runs" },
  { href: "/configuracoes", label: "Configurações" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Fecha o drawer ao trocar de rota (em mobile o usuário acabou de navegar).
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // ESC fecha drawer.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Trava scroll do body quando drawer está aberto em mobile.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        className="sidebar-toggle"
        aria-label="abrir menu"
        aria-expanded={open}
        aria-controls="primary-sidebar"
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden="true">☰</span>
      </button>

      {open && (
        <div
          className="sidebar-overlay"
          aria-hidden="true"
          onClick={() => setOpen(false)}
        />
      )}

      <aside
        id="primary-sidebar"
        className={open ? "sidebar sidebar-open" : "sidebar"}
      >
        <h1>youtube-analyzer</h1>
        <nav>
          {items.map((it) => {
            const active =
              it.href === "/" ? pathname === "/" : pathname?.startsWith(it.href);
            return (
              <Link
                key={it.href}
                href={it.href}
                className={active ? "active" : undefined}
              >
                {it.label}
              </Link>
            );
          })}
        </nav>
      </aside>
    </>
  );
}
