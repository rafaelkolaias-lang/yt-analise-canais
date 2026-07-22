import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { ConfirmProvider } from "@/components/ConfirmDialog";
import { ToasterProvider } from "@/components/Toaster";
import { VideoPlayerProvider } from "@/components/VideoPlayerModal";
import "./globals.css";

export const metadata: Metadata = {
  title: "RK Youtube Analyzer",
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
          <ConfirmProvider>
            <VideoPlayerProvider>
              <AppShell>{children}</AppShell>
            </VideoPlayerProvider>
          </ConfirmProvider>
        </ToasterProvider>
      </body>
    </html>
  );
}
