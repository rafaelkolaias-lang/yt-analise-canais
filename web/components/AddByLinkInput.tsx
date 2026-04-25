"use client";

import { useState } from "react";

import { useToast } from "@/components/Toaster";
import {
  apiPost,
  type MonitoredChannel,
  type MonitoredVideo,
  type ResolveResult,
} from "@/lib/api";

type Props = {
  /**
   * Disparado quando um canal é adicionado com sucesso. Use pra atualizar
   * a lista da tela.
   */
  onChannelAdded?: (c: MonitoredChannel) => void;
  /**
   * Disparado quando um vídeo é adicionado. Como o backend cria o canal
   * dono automaticamente, é boa prática disparar também `onChannelAdded`
   * caso a tela queira recarregar canais.
   */
  onVideoAdded?: (v: MonitoredVideo) => void;
};

export function AddByLinkInput({ onChannelAdded, onVideoAdded }: Props) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const raw = value.trim();
    if (!raw) return;

    setBusy(true);
    try {
      // 1) Resolve o input (parse local + handle se preciso)
      const resolved = await apiPost<ResolveResult>(
        "/api/monitoring/resolve",
        { raw }
      );

      // 2) Adiciona conforme o tipo
      if (resolved.kind === "channel") {
        const channel = await apiPost<MonitoredChannel>(
          "/api/monitoring/channels",
          { youtube_channel_id: resolved.youtube_id }
        );
        toast.success(`Canal adicionado: ${channel.title || resolved.youtube_id}`);
        setValue("");
        onChannelAdded?.(channel);
      } else {
        const video = await apiPost<MonitoredVideo>(
          "/api/monitoring/videos",
          { youtube_video_id: resolved.youtube_id }
        );
        toast.success(
          `Vídeo adicionado: ${video.title.slice(0, 60)}${video.title.length > 60 ? "…" : ""}`
        );
        setValue("");
        onVideoAdded?.(video);
        // Backend criou o canal dono automaticamente — vale dar refresh
        // (caller pode escolher implementar ou não).
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className="card"
      style={{
        display: "flex",
        gap: 8,
        alignItems: "center",
        padding: 12,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <input
          type="text"
          className="input"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Cole link ou ID do canal/vídeo (ex.: youtube.com/@nome, watch?v=…, UC…)"
          disabled={busy}
          style={{ width: "100%" }}
        />
      </div>
      <button
        type="submit"
        className="btn-primary"
        disabled={busy || value.trim().length === 0}
      >
        {busy ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span className="spinner" aria-hidden />
            Adicionando…
          </span>
        ) : (
          "+ Adicionar"
        )}
      </button>
    </form>
  );
}
