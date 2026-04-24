"use client";

type Props = {
  message: string;
  onRetry?: () => void;
  title?: string;
};

export function ErrorCard({ message, onRetry, title = "Algo deu errado" }: Props) {
  return (
    <div className="card error-card" role="alert">
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="status-pill danger">erro</span>
        <strong style={{ fontSize: 13 }}>{title}</strong>
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 6, wordBreak: "break-word" }}>
        {message}
      </div>
      {onRetry && (
        <div style={{ marginTop: 10 }}>
          <button type="button" className="btn-ghost" onClick={onRetry}>
            Tentar de novo
          </button>
        </div>
      )}
    </div>
  );
}
