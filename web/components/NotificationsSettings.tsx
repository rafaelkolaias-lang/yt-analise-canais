"use client";

import { useToast } from "@/components/Toaster";
import { useBrowserNotifications } from "@/lib/useBrowserNotifications";

function permissionLabel(state: string): { text: string; tone: string } {
  switch (state) {
    case "unsupported":
      return { text: "navegador não suporta", tone: "danger" };
    case "denied":
      return { text: "bloqueado no navegador", tone: "danger" };
    case "granted":
      return { text: "permissão concedida", tone: "success" };
    default:
      return { text: "permissão ainda não solicitada", tone: "warn" };
  }
}

export function NotificationsSettings() {
  const { permission, enabled, setEnabled, requestPermission } =
    useBrowserNotifications();
  const toast = useToast();

  const label = permissionLabel(permission);
  const supported = permission !== "unsupported";
  const canEnable = supported && permission !== "denied";

  async function onToggle() {
    // Caminho 1: ainda não pediu permissão -> pede e, se conceder, ativa.
    if (permission === "default") {
      const result = await requestPermission();
      if (result === "granted") {
        setEnabled(true);
        toast.success("Notificações ativadas.");
      } else if (result === "denied") {
        toast.error(
          "Permissão negada. Ative manualmente nas configurações do navegador."
        );
      }
      return;
    }
    // Caminho 2: já tem permissão -> só alterna a preferência local.
    if (permission === "granted") {
      const next = !enabled;
      setEnabled(next);
      toast.success(next ? "Notificações ativadas." : "Notificações desativadas.");
      return;
    }
    // Caminho 3: denied/unsupported -> nada a fazer.
    if (permission === "denied") {
      toast.error(
        "Notificações estão bloqueadas no navegador. Desbloqueie nas configurações do site."
      );
    }
  }

  return (
    <section className="card">
      <header style={{ marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 15 }}>Notificações do navegador</h3>
        <p className="muted" style={{ margin: "2px 0 0", fontSize: 12 }}>
          Receba alertas no PC ou celular quando o sync terminar. Funciona
          enquanto a aba estiver aberta. Preferência salva localmente neste
          navegador.
        </p>
      </header>
      <div className="settings-row">
        <div className="settings-meta">
          <div style={{ fontSize: 13, fontWeight: 500 }}>
            Ativar notificações
          </div>
          <div
            className={`muted notif-perm-${label.tone}`}
            style={{ fontSize: 11, marginTop: 4 }}
          >
            Status: {label.text}
            {enabled && permission === "granted" && " · ativadas"}
            {!enabled && permission === "granted" && " · desativadas"}
          </div>
        </div>
        <div className="settings-control">
          <button
            type="button"
            className={enabled && canEnable ? "btn-primary" : "btn-ghost"}
            onClick={onToggle}
            disabled={!supported}
          >
            {!supported
              ? "Indisponível"
              : permission === "denied"
              ? "Bloqueado"
              : enabled && permission === "granted"
              ? "Desativar"
              : permission === "default"
              ? "Pedir permissão"
              : "Ativar"}
          </button>
        </div>
      </div>
    </section>
  );
}
