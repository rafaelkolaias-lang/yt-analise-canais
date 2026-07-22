"use client";

import { usePathname } from "next/navigation";

import { GlobalSyncIndicator } from "@/components/GlobalSyncIndicator";
import { NotificationsCenter } from "@/components/NotificationsCenter";
import { Sidebar } from "@/components/Sidebar";

/**
 * Shell da aplicação (sidebar + indicadores + central de notificações).
 *
 * Na página /login o shell é omitido: além de visual, evita que os pollings
 * (notificações, quota, versão) fiquem batendo na API sem token e enchendo o
 * console de 401.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  if (pathname === "/login") {
    return <>{children}</>;
  }

  return (
    <>
      <div className="app-shell">
        <Sidebar />
        <main className="main">
          <GlobalSyncIndicator />
          {children}
        </main>
      </div>
      <NotificationsCenter />
    </>
  );
}
