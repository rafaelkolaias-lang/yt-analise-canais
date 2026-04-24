"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

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
  return (
    <aside className="sidebar">
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
  );
}
