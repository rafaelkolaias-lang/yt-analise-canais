"use client";

import { useCallback, useEffect, useState } from "react";

export type NotificationPermissionState =
  | "unsupported"
  | "default"
  | "granted"
  | "denied";

const STORAGE_KEY = "notifications.enabled";

function readEnabled(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeEnabled(v: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, v ? "1" : "0");
  } catch {
    /* ignore */
  }
}

function readPermission(): NotificationPermissionState {
  if (typeof window === "undefined") return "default";
  if (typeof Notification === "undefined") return "unsupported";
  return Notification.permission;
}

/**
 * Estado do recurso de notificações do browser, com persistência local da
 * preferência do usuário (`enabled`). A preferência é per-device/per-browser
 * — não faz sentido sincronizar com banco.
 *
 * Notification API real só funciona enquanto a aba estiver aberta. Para
 * entrega em background completa, seria necessário Service Worker + Web
 * Push (ver !projeto.md, armadilha conhecida).
 */
export function useBrowserNotifications() {
  const [permission, setPermission] = useState<NotificationPermissionState>(
    "default"
  );
  const [enabled, setEnabledState] = useState(false);

  // Inicializa após mount (SSR-safe).
  useEffect(() => {
    setPermission(readPermission());
    setEnabledState(readEnabled());
  }, []);

  const setEnabled = useCallback((v: boolean) => {
    writeEnabled(v);
    setEnabledState(v);
  }, []);

  const requestPermission = useCallback(async (): Promise<NotificationPermissionState> => {
    if (typeof Notification === "undefined") return "unsupported";
    if (Notification.permission === "granted" || Notification.permission === "denied") {
      setPermission(Notification.permission);
      return Notification.permission;
    }
    const result = await Notification.requestPermission();
    setPermission(result);
    return result;
  }, []);

  const canSend = permission === "granted" && enabled;

  const send = useCallback(
    (title: string, options?: NotificationOptions) => {
      if (!canSend) return;
      try {
        new Notification(title, options);
      } catch {
        /* alguns browsers em http: bloqueiam — silenciar */
      }
    },
    [canSend]
  );

  return { permission, enabled, setEnabled, requestPermission, send, canSend };
}
