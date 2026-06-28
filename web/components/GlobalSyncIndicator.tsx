"use client";

import { useEffect, useRef, useState } from "react";

import { apiGet, type SyncRun, type SyncStatus } from "@/lib/api";
import { useBrowserNotifications } from "@/lib/useBrowserNotifications";

const POLL_INTERVAL_MS = 5000;

function notificationBodyFor(run: SyncRun): string {
  const parts: string[] = [];
  if (run.channels_processed > 0) parts.push(`${run.channels_processed} canais`);
  if (run.videos_processed > 0) parts.push(`${run.videos_processed} vídeos`);
  if (parts.length === 0) return run.notes ?? "Sem itens processados.";
  return parts.join(" · ");
}

function notificationTitleFor(run: SyncRun): string {
  switch (run.status) {
    case "success":
      return "Sync concluído ✓";
    case "partial":
      return "Sync concluído com falhas parciais";
    case "failed":
      return "Sync falhou";
    default:
      return "Sync atualizado";
  }
}

export function GlobalSyncIndicator() {
  const [running, setRunning] = useState(false);
  const [channels, setChannels] = useState<number>(0);
  const lastRunIdRef = useRef<number | null>(null);
  const lastRunStatusRef = useRef<SyncRun["status"] | null>(null);
  const { send: sendNotification } = useBrowserNotifications();

  useEffect(() => {
    let cancelled = false;

    async function tick() {
      try {
        const s = await apiGet<SyncStatus>("/api/sync/status");
        if (cancelled) return;
        const last = s.last_run;
        const isRunning = last?.status === "running";
        setRunning(isRunning);
        setChannels(last?.channels_processed ?? 0);

        if (last) {
          const prevStatus = lastRunStatusRef.current;
          const prevId = lastRunIdRef.current;
          // Detecta transição "running" -> qualquer estado terminal, ou run
          // novo (id mudou) já vindo terminado.
          const transitionedToDone =
            (prevStatus === "running" && last.status !== "running") ||
            (prevId !== null && prevId !== last.id && last.status !== "running");
          // Notificação nativa só para sync AGENDADO (background): o sync manual
          // já dá feedback via toast no próprio dashboard — notificar de novo
          // duplicaria o aviso do mesmo evento.
          if (transitionedToDone && last.type !== "manual") {
            sendNotification(notificationTitleFor(last), {
              body: notificationBodyFor(last),
              tag: `sync-${last.id}`,
            });
          }
          lastRunIdRef.current = last.id;
          lastRunStatusRef.current = last.status;
        }
      } catch {
        if (!cancelled) setRunning(false);
      }
    }

    tick();
    const handle = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [sendNotification]);

  if (!running) return null;

  return (
    <div className="global-sync-indicator" role="status" aria-live="polite">
      <span className="spinner" aria-hidden />
      <span>
        Sincronizando…
        {channels > 0 && (
          <span className="muted" style={{ marginLeft: 6, fontSize: 11 }}>
            {channels} canais processados
          </span>
        )}
      </span>
    </div>
  );
}
