"use client";

import { useEffect, useRef, useState } from "react";

import { apiGet, type SyncStatus } from "@/lib/api";

const POLL_INTERVAL_MS = 5000;

export function GlobalSyncIndicator() {
  const [running, setRunning] = useState(false);
  const [channels, setChannels] = useState<number>(0);
  const lastRunIdRef = useRef<number | null>(null);

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
        if (last && last.id !== lastRunIdRef.current) {
          lastRunIdRef.current = last.id;
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
  }, []);

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
