import type { Metadata } from "next";
import { GlobalSyncIndicator } from "@/components/GlobalSyncIndicator";
import { Sidebar } from "@/components/Sidebar";
import { ToasterProvider } from "@/components/Toaster";
import "./globals.css";

export const metadata: Metadata = {
  title: "youtube-analyzer",
  description: "Descoberta, monitoramento e analytics de canais do YouTube",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR">
      <body>
        <ToasterProvider>
          <div className="app-shell">
            <Sidebar />
            <main className="main">
              <GlobalSyncIndicator />
              {children}
            </main>
          </div>
        </ToasterProvider>
      </body>
    </html>
  );
}
