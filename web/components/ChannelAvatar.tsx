"use client";

type Props = {
  url: string | null | undefined;
  title: string;
  size?: number;
};

/**
 * Avatar circular do canal. Usa thumbnail_url do banco; se não houver,
 * mostra um círculo com a inicial do título — evita "imagem quebrada".
 */
export function ChannelAvatar({ url, title, size = 32 }: Props) {
  const initial = (title || "?").trim().charAt(0).toUpperCase() || "?";
  const style: React.CSSProperties = {
    width: size,
    height: size,
    borderRadius: "50%",
    flexShrink: 0,
    objectFit: "cover",
    background: "var(--bg)",
    border: "1px solid var(--border)",
  };

  if (url) {
    return (
      <img
        src={url}
        alt=""
        width={size}
        height={size}
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
        fontSize: Math.max(11, Math.round(size * 0.4)),
        fontWeight: 600,
      }}
    >
      {initial}
    </span>
  );
}
