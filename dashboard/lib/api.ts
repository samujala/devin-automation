const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface Metrics {
  total_findings: number;
  issues_filed: number;
  sessions_started: number;
  sessions_completed: number;
  sessions_in_progress: number;
  sessions_failed: number;
  prs_opened: number;
  prs_merged: number;
  success_rate: number | null;
  avg_duration_seconds: number | null;
  total_duration_seconds: number;
  estimated_acus: number;
}

export interface ThroughputPoint {
  date: string;
  prs_opened: number;
  prs_merged: number;
  failed: number;
}

export interface LiveSession {
  session_id: string;
  batch_key: string;
  rule: string;
  title: string;
  started_at: string;
  elapsed_seconds: number;
  status: string;
  status_enum: string | null;
  session_url: string | null;
}

export interface RecentSession {
  session_id: string;
  batch_key: string;
  rule: string;
  title: string;
  pr_url: string | null;
  pr_number: number | null;
  duration_seconds: number | null;
  outcome: string;
  finished_at: string;
  merged_at: string | null;
}

export interface FailedByRule {
  rule: string;
  failed_count: number;
}

export interface FailedDetail {
  session_id: string;
  batch_key: string;
  rule: string;
  reason: string;
  session_url: string | null;
  finished_at: string | null;
}

export interface FailedSessions {
  by_rule: FailedByRule[];
  detail: FailedDetail[];
}

export interface OrchestratorStatusData {
  is_alive: boolean;
  last_poll_at: string | null;
  started_at: string | null;
  poll_count: number;
  seconds_since_poll: number | null;
}

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function apiPost<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  metrics: () => apiFetch<Metrics>("/api/metrics"),
  throughput: (days = 14) => apiFetch<ThroughputPoint[]>(`/api/sessions/throughput?days=${days}`),
  live: () => apiFetch<LiveSession[]>("/api/sessions/live"),
  recent: (limit = 10) => apiFetch<RecentSession[]>(`/api/sessions/recent?limit=${limit}`),
  failed: (days = 14) => apiFetch<FailedSessions>(`/api/sessions/failed?days=${days}`),
  orchestratorStatus: () => apiFetch<OrchestratorStatusData>("/api/orchestrator/status"),
  startOrchestrator: () => apiPost<{ ok: boolean; message: string }>("/api/orchestrator/start"),
  stopOrchestrator: () => apiPost<{ ok: boolean; message: string }>("/api/orchestrator/stop"),
};
