"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { QuotaSidebarWidget } from "@/components/QuotaSidebarWidget";
import { apiPost } from "@/lib/api";
import { clearToken } from "@/lib/authToken";

type NavChild = { href: string; label: string };
type NavItem = { href: string; label: string; children?: NavChild[] };

// Itens com `children` viram grupo retrátil: o item pai só abre/fecha, quem
// navega são os filhos.
const items: NavItem[] = [
  { href: "/", label: "Dashboard" },
  { href: "/descoberta", label: "Descoberta" },
  { href: "/monitoramento", label: "Monitoramento" },
  { href: "/sugestoes", label: "Sugestões" },
  {
    href: "/analytics",
    label: "Analytics",
    children: [
      { href: "/analytics", label: "Canais" },
      { href: "/analytics/videos", label: "Vídeos por canal" },
    ],
  },
  { href: "/runs", label: "Runs" },
  { href: "/configuracoes", label: "Configurações" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  // Grupos retráteis abertos (por href do pai). Começa fechado; o efeito
  // abaixo abre sozinho o grupo da rota atual.
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

  // Ao entrar numa rota que pertence a um grupo, o grupo já aparece aberto —
  // senão o item ativo ficaria escondido.
  useEffect(() => {
    const inGroup = items.find(
      (it) => it.children && pathname?.startsWith(it.href)
    );
    if (inGroup) setOpenGroups((prev) => ({ ...prev, [inGroup.href]: true }));
  }, [pathname]);

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
        <h1>RK Youtube Analyzer</h1>
        <nav>
          {items.map((it) => {
            const active =
              it.href === "/" ? pathname === "/" : pathname?.startsWith(it.href);

            if (!it.children) {
              return (
                <Link
                  key={it.href}
                  href={it.href}
                  className={active ? "active" : undefined}
                >
                  {it.label}
                </Link>
              );
            }

            const expanded = !!openGroups[it.href];
            return (
              <div key={it.href} className="nav-group">
                <button
                  type="button"
                  className={`nav-group-toggle${active ? " active" : ""}`}
                  aria-expanded={expanded}
                  onClick={() =>
                    setOpenGroups((prev) => ({ ...prev, [it.href]: !expanded }))
                  }
                >
                  <span>{it.label}</span>
                  <span className="nav-group-caret" aria-hidden="true">
                    {expanded ? "▾" : "▸"}
                  </span>
                </button>
                {expanded && (
                  <div className="nav-group-children">
                    {it.children.map((child) => (
                      <Link
                        key={child.href}
                        href={child.href}
                        className={pathname === child.href ? "active" : undefined}
                      >
                        {child.label}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
        <QuotaSidebarWidget />
        <button
          type="button"
          className="muted"
          style={{
            marginTop: 12,
            background: "none",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "6px 10px",
            fontSize: 12,
            cursor: "pointer",
            color: "inherit",
          }}
          onClick={async () => {
            // Revoga a sessão no servidor (melhor esforço) e limpa local.
            try {
              await apiPost("/api/auth/logout", {});
            } catch {
              /* sessão pode já estar inválida — segue o logout local */
            }
            clearToken();
            window.location.href = "/login";
          }}
        >
          Sair
        </button>
      </aside>
    </>
  );
}
