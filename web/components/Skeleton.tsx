"use client";

type Props = {
  width?: string | number;
  height?: string | number;
  radius?: string | number;
  style?: React.CSSProperties;
  className?: string;
};

export function Skeleton({
  width = "100%",
  height = 14,
  radius = 4,
  style,
  className,
}: Props) {
  return (
    <span
      className={`skeleton${className ? ` ${className}` : ""}`}
      style={{
        width,
        height,
        borderRadius: radius,
        ...style,
      }}
      aria-hidden
    />
  );
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="card">
      <Skeleton width="40%" height={16} />
      <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} width={i === lines - 1 ? "70%" : "100%"} />
        ))}
      </div>
    </div>
  );
}
