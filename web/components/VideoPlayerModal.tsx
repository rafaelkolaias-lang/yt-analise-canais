"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

type PlayArgs = {
  videoId: string;
  title?: string | null;
  /** Link "assistir no YouTube". Se ausente, é derivado do videoId. */
  watchUrl?: string | null;
};

type PlayFn = (args: PlayArgs) => void;

const VideoPlayerContext = createContext<PlayFn>(() => {});

/**
 * Hook para abrir o player de vídeo embutido (modal). Uso:
 *   const play = useVideoPlayer();
 *   play({ videoId, title, watchUrl });
 */
export function useVideoPlayer(): PlayFn {
  return useContext(VideoPlayerContext);
}

export function VideoPlayerProvider({ children }: { children: React.ReactNode }) {
  const [current, setCurrent] = useState<PlayArgs | null>(null);

  const play = useCallback<PlayFn>((args) => setCurrent(args), []);
  const close = useCallback(() => setCurrent(null), []);

  // Fecha com Escape.
  useEffect(() => {
    if (!current) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, close]);

  const watchUrl = current
    ? current.watchUrl || `https://www.youtube.com/watch?v=${current.videoId}`
    : "#";

  return (
    <VideoPlayerContext.Provider value={play}>
      {children}
      {current && (
        <div className="modal-overlay" role="presentation" onClick={close}>
          <div
            className="video-modal-card"
            role="dialog"
            aria-modal="true"
            aria-label={current.title ?? "Vídeo"}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="video-modal-head">
              <span className="video-modal-title" title={current.title ?? undefined}>
                {current.title ?? "Vídeo"}
              </span>
              <button
                type="button"
                className="btn-ghost"
                onClick={close}
                aria-label="Fechar"
              >
                ✕
              </button>
            </div>
            <div className="video-modal-frame">
              {/* Player oficial do YouTube — não consome cota da Data API.
                  Vídeos com embed bloqueado pelo dono mostram a mensagem do
                  próprio YouTube; o botão abaixo é o fallback garantido. */}
              <iframe
                src={`https://www.youtube.com/embed/${current.videoId}?autoplay=1&rel=0`}
                title={current.title ?? "Vídeo"}
                allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
                allowFullScreen
              />
            </div>
            <div className="video-modal-actions">
              <a
                className="btn-primary"
                href={watchUrl}
                target="_blank"
                rel="noreferrer"
              >
                Assistir no YouTube ↗
              </a>
            </div>
          </div>
        </div>
      )}
    </VideoPlayerContext.Provider>
  );
}
