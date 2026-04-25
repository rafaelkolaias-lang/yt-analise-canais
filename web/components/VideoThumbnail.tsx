"use client";

type Props = {
  url: string | null | undefined;
  title: string;
  width?: number;
};

/**
 * Thumbnail do vídeo (16:9). Usa thumbnail_url do banco; se vazio, mostra
 * placeholder cinza com o título truncado.
 */
export function VideoThumbnail({ url, title, width = 120 }: Props) {
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

  if (url) {
    return (
      <img
        src={url}
        alt=""
        width={width}
        height={height}
        loading="lazy"
        style={style}
        referrerPolicy="no-referrer"
      />
    );
  }

  return (
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
}
