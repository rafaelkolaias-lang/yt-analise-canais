"use client";

import { useVideoPlayer } from "@/components/VideoPlayerModal";

type Props = {
  url: string | null | undefined;
  title: string;
  width?: number;
  /** ID do vídeo no YouTube. Se presente, mostra o botão ▶ que abre o player
   *  embutido (modal). Sem ele, a thumbnail é só imagem (comportamento antigo). */
  videoId?: string | null;
  /** Link "assistir no YouTube" usado no modal (fallback derivado do videoId). */
  watchUrl?: string | null;
};

/**
 * Thumbnail do vídeo (16:9). Usa thumbnail_url do banco; se vazio, mostra
 * placeholder cinza. Com `videoId`, ganha um botão ▶ que abre o player do
 * YouTube dentro do site.
 */
export function VideoThumbnail({ url, title, width = 120, videoId, watchUrl }: Props) {
  const play = useVideoPlayer();
  const height = Math.round((width * 9) / 16);
  const style: React.CSSProperties = {
    width,
    height,
    flexShrink: 0,
    objectFit: "cover",
    borderRadius: 4,
    background: "var(--bg)",
    border: "1px solid var(--border)",
  };

  const inner = url ? (
    <img
      src={url}
      alt=""
      width={width}
      height={height}
      loading="lazy"
      style={style}
      referrerPolicy="no-referrer"
    />
  ) : (
    <span
      aria-hidden
      style={{
        ...style,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        color: "var(--text-dim)",
        fontSize: 10,
        textAlign: "center",
        padding: 4,
        overflow: "hidden",
      }}
    >
      sem thumb
    </span>
  );

  // Sem videoId: mantém o comportamento antigo (só a imagem).
  if (!videoId) return inner;

  return (
    <span
      className="video-thumb-wrap"
      style={{ width, height, flexShrink: 0, display: "inline-block", position: "relative" }}
    >
      {inner}
      <button
        type="button"
        className="video-thumb-play"
        aria-label={`Assistir "${title}" dentro do site`}
        title="Assistir aqui"
        onClick={(e) => {
          // Evita acionar um <a> que envolva a thumbnail em alguns lugares.
          e.preventDefault();
          e.stopPropagation();
          play({ videoId, title, watchUrl });
        }}
      >
        ▶
      </button>
    </span>
  );
}
