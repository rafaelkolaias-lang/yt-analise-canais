export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`GET ${path} falhou: ${res.status}`);
  }
  return res.json();
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`PUT ${path} falhou: ${res.status} ${text}`);
  }
  return res.json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`POST ${path} falhou: ${res.status} ${text}`);
  }
  return res.json();
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`PATCH ${path} falhou: ${res.status} ${text}`);
  }
  return res.json();
}

export async function apiDelete(path: string): Promise<void> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "DELETE",
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`DELETE ${path} falhou: ${res.status} ${text}`);
  }
}

export type AppSetting = {
  key: string;
  value: string | null;
  value_type: string;
  is_secret: boolean;
  has_value: boolean;
  description: string | null;
  updated_at: string;
};

// =============================================================================
// Discovery
// =============================================================================

export type DiscoveryDefaults = {
  window_days: number;
  min_views: number;
  min_vpd: number;
  min_duration_seconds: number;
  languages: string[];
  pages_per_term: number;
};

export type DiscoverySearchRequest = {
  terms: string[];
  window_days?: number;
  min_views?: number;
  min_vpd?: number;
  min_duration_seconds?: number;
  languages?: string[];
  pages_per_term?: number;
};

export type ResultChannel = {
  id: number;
  youtube_channel_id: string;
  title: string;
  url: string | null;
  subscribers: number | null;
  views_total: number | null;
  video_count: number | null;
  captured_at: string;
};

export type ResultVideo = {
  id: number;
  youtube_video_id: string;
  youtube_channel_id: string | null;
  title: string;
  url: string | null;
  views: number | null;
  likes: number | null;
  duration_seconds: number | null;
  published_at: string | null;
  vpd: number | null;
  matched_term: string | null;
  captured_at: string;
};

export type DiscoveryRun = {
  id: number;
  terms: string;
  status: "running" | "success" | "failed";
  started_at: string;
  finished_at: string | null;
  channels_found: number;
  videos_found: number;
  notes: string | null;
  filters_json: string | null;
  channel_results: ResultChannel[];
  video_results: ResultVideo[];
};

// =============================================================================
// Monitoring
// =============================================================================

export type MonitoredChannel = {
  id: number;
  youtube_channel_id: string;
  title: string;
  url: string | null;
  custom_url: string | null;
  thumbnail_url: string | null;
  status: string;
  is_active: boolean;
  source: string | null;
  created_at: string;
  updated_at: string;
  // Estendido com último snapshot (GET /api/monitoring/channels)
  subscribers?: number | null;
  views_total?: number | null;
  video_count?: number | null;
  avg_vpd_recent?: number | null;
  delta_subscribers?: number | null;
  delta_views_total?: number | null;
  last_snapshot_at?: string | null;
};

export type MonitoredVideo = {
  id: number;
  channel_id: number;
  youtube_video_id: string;
  title: string;
  url: string | null;
  thumbnail_url: string | null;
  status: string;
  tracking_source: string | null;
  first_tracked_at: string;
  first_tracked_vpd?: number | null;
  last_seen_vpd?: number | null;
  last_seen_views?: number | null;
  last_seen_at?: string | null;
};

export type ChannelSnapshot = {
  id: number;
  channel_id: number;
  subscribers: number | null;
  views_total: number | null;
  video_count: number | null;
  avg_vpd_recent: number | null;
  delta_subscribers: number | null;
  delta_views_total: number | null;
  captured_at: string;
};

export type VideoSnapshot = {
  id: number;
  tracked_video_id: number;
  views: number | null;
  likes: number | null;
  comments: number | null;
  vpd: number | null;
  delta_views: number | null;
  delta_likes: number | null;
  delta_comments: number | null;
  captured_at: string;
};

// =============================================================================
// Sync
// =============================================================================

export type SyncRun = {
  id: number;
  type: "manual" | "scheduled";
  status: "running" | "success" | "partial" | "failed";
  started_at: string;
  finished_at: string | null;
  channels_processed: number;
  videos_processed: number;
  notes: string | null;
};

export type SyncStatus = {
  interval_hours: number;
  next_run_at: string | null;
  last_run: SyncRun | null;
};

// Runs de discovery (resumo, para a página Runs)
export type DiscoveryRunSummary = {
  id: number;
  terms: string;
  status: "running" | "success" | "failed";
  started_at: string;
  finished_at: string | null;
  channels_found: number;
  videos_found: number;
  notes: string | null;
};

// =============================================================================
// Analytics
// =============================================================================

export type AnalyticsOverview = {
  channels_total: number;
  channels_accelerating: number;
  channels_promising: number;
  channels_saturated: number;
  channels_stable: number;
  channels_unknown: number;
  videos_accelerating: number;
};

export type TimeseriesPoint = {
  captured_at: string | null;
  value: number | null;
};

export type AnalyticsMetric =
  | "subscribers"
  | "views_total"
  | "avg_vpd_recent"
  | "uploads_per_week";

export type GrowthPair = {
  current: number | null;
  pct_7d: number | null;
  pct_30d: number | null;
};

export type ChannelAnalyticsSummary = {
  channel_id: number;
  total_snapshots: number;
  last_captured_at: string | null;
  signal: "heating" | "promising" | "saturated" | "stable" | null;
  signal_reason: string | null;
  subscribers: GrowthPair;
  views_total: GrowthPair;
  avg_vpd_recent: GrowthPair;
  uploads_per_week: number | null;
};

export type NicheRow = {
  tag_id: number;
  tag_name: string;
  channels_count: number;
  avg_subscribers: number | null;
  avg_vpd: number | null;
};
