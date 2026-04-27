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

export async function apiDeleteJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "DELETE",
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`DELETE ${path} falhou: ${res.status} ${text}`);
  }
  return res.json();
}

export type AppSetting = {
  key: string;
  value: string | null;
  value_type: string;
  is_secret: boolean;
  has_value: boolean;
  description: string | null;
  help: string | null;
  updated_at: string;
};

// =============================================================================
// YouTube API keys (gerenciamento individual)
// =============================================================================
export type YouTubeKeyStatus = "ok" | "quota_exhausted" | "burned";

export type YouTubeKeyEntry = {
  fingerprint: string;
  masked: string;
  index: number;
  status: YouTubeKeyStatus;
  used_today: number;
  daily_quota: number;
  burned_at: string | null;
  burned_reason: string | null;
  burned_label: string | null;
};

export type YouTubeKeyAddResponse = {
  entry: YouTubeKeyEntry;
  created: boolean;
};

export type YouTubeKeyOpResponse = {
  fingerprint: string;
  changed: boolean;
};

export type YouTubeKeysHealth = {
  total: number;
  ok: number;
  quota_exhausted: number;
  burned: number;
  last_burned_at: string | null;
  last_burned_reason: string | null;
};

// =============================================================================
// Notificações persistentes (tabela `notifications`)
// =============================================================================
export type NotificationStatus = "running" | "success" | "error" | "info";

export type NotificationType =
  | "task_progress"
  | "task_done"
  | "task_error"
  | "system_alert"
  | "suggestions_changed"
  | string; // permite tipos novos sem refator

export type NotificationItem = {
  id: number;
  type: NotificationType;
  status: NotificationStatus;
  title: string;
  message: string | null;
  progress_pct: number | null;
  metadata_json: string | null;
  source_key: string | null;
  created_at: string;
  updated_at: string;
  read_at: string | null;
  dismissed_at: string | null;
};

export type NotificationsListResponse = {
  items: NotificationItem[];
  unread_count: number;
};

export type UnreadCountResponse = { unread_count: number };

export type NotificationOpResponse = { id: number; changed: boolean };

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
  min_channel_age_days: number;
  max_channel_age_days: number;
};

export type DiscoverySearchRequest = {
  terms: string[];
  window_days?: number;
  min_views?: number;
  min_vpd?: number;
  min_duration_seconds?: number;
  languages?: string[];
  pages_per_term?: number;
  min_channel_age_days?: number;
  max_channel_age_days?: number;
};

export type ResultChannel = {
  id: number;
  youtube_channel_id: string;
  title: string;
  url: string | null;
  thumbnail_url: string | null;
  subscribers: number | null;
  views_total: number | null;
  video_count: number | null;
  captured_at: string;
  reviewed_at: string | null;
};

export type ResultVideo = {
  id: number;
  youtube_video_id: string;
  youtube_channel_id: string | null;
  title: string;
  url: string | null;
  thumbnail_url: string | null;
  views: number | null;
  likes: number | null;
  duration_seconds: number | null;
  published_at: string | null;
  vpd: number | null;
  matched_term: string | null;
  captured_at: string;
  reviewed_at: string | null;
};

export type ReviewProgress = {
  channels_total: number;
  channels_reviewed: number;
  videos_total: number;
  videos_reviewed: number;
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
  progress: ReviewProgress;
};

export type BlacklistEntry = {
  id: number;
  youtube_channel_id: string;
  reason: string | null;
  blacklisted_at: string;
};

// =============================================================================
// Suggestions (recomendações de monitoramento)
// =============================================================================

export type MonitorSuggestion = {
  youtube_channel_id: string;
  title: string;
  url: string | null;
  thumbnail_url: string | null;
  subscribers: number | null;
  video_count: number | null;
  avg_vpd_recent: number | null;
  channel_published_at: string | null;
  discovery_result_id: number;
  matched_term: string | null;
  suggestion_kind: string;
  top_video_title: string | null;
  top_video_url: string | null;
  top_video_views: number | null;
  top_video_vpd: number | null;
  reason: string;
};

export type DeadChannelSuggestion = {
  channel_id: number;
  youtube_channel_id: string;
  title: string;
  url: string | null;
  thumbnail_url: string | null;
  status: string;
  last_snapshot_at: string | null;
  last_upload_at: string | null;
  days_since_last_upload: number | null;
  avg_vpd_recent: number | null;
  signal: string | null;
  reason: string;
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
  notes: string | null;
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
  unavailable_reason: string | null;
  unavailable_since: string | null;
  channel_title: string | null;
  channel_url: string | null;
  status: string;
  tracking_source: string | null;
  first_tracked_at: string;
  first_tracked_vpd?: number | null;
  last_seen_vpd?: number | null;
  last_seen_views?: number | null;
  last_seen_at?: string | null;
};

export type BulkOperationError = {
  id: number;
  message: string;
};

export type BulkOperationResponse = {
  total: number;
  success_count: number;
  error_count: number;
  processed_ids: number[];
  errors: BulkOperationError[];
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
  // Saude do scheduler in-process. `false` = trigger provavelmente incorreto;
  // dashboard mostra aviso e `next_run_at` pode mentir.
  scheduler_ok?: boolean;
  scheduler_error?: string | null;
};

// Resolve (input do usuário → canal ou vídeo)
export type ResolveResult = {
  kind: "channel" | "video";
  youtube_id: string;
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

// Versão estendida com progresso de revisão (vinda de GET /api/discovery/runs)
export type DiscoveryRunWithProgress = DiscoveryRunSummary & {
  progress: ReviewProgress;
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
  pct_90d: number | null;
};

export type GrowthConsistency = {
  positive_windows: number;
  available_windows: number;
  label: string;
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
  median_recent_views: number | null;
  recent_uploads_considered: number;
  subscribers_consistency: GrowthConsistency;
  views_consistency: GrowthConsistency;
  breakout_candidate: boolean;
  breakout_reason: string | null;
};

export type NicheRow = {
  tag_id: number;
  tag_name: string;
  channels_count: number;
  avg_subscribers: number | null;
  avg_vpd: number | null;
};

export type ChannelAnalyticsBasic = {
  id: number;
  youtube_channel_id: string;
  title: string;
  url: string | null;
  thumbnail_url: string | null;
};

export type ChannelAnalyticsBundle = {
  channel: ChannelAnalyticsBasic;
  summary: ChannelAnalyticsSummary;
  subscribers_series: TimeseriesPoint[];
  views_series: TimeseriesPoint[];
  vpd_series: TimeseriesPoint[];
  uploads_series: TimeseriesPoint[];
};

export type PaginatedChannelAnalytics = {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  items: ChannelAnalyticsBundle[];
};

// =============================================================================
// Notifications (central operacional)
// =============================================================================

export type QuotaUsageEvent = {
  at: string;
  label: string;
  cost: number;
  key_index: number;
};

export type QuotaSummary = {
  date_utc: string;
  keys_count: number;
  daily_quota_per_key: number;
  total_quota: number;
  used: number;
  remaining: number;
  used_per_key: number[];
  last_event: QuotaUsageEvent | null;
};

// =============================================================================
// Versao da API (heartbeat para detectar offline / redeploy)
// =============================================================================

export type ApiVersionResponse = {
  version: string;
  started_at: string | null;
};
