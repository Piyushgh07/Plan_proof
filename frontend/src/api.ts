export type QueryRow = {
  queryid: string;
  sql: string;
  calls: number;
  total_exec_time_ms: number;
  mean_exec_time_ms: number;
  rows: number;
  analyzable: boolean;
  reason: string | null;
};

export type Candidate = {
  id?: string;
  table: string;
  columns: string[];
  proposal_sql?: string | null;
  source?: string;
  rationale?: string | null;
  decision: string;
  reason: string;
  comparison_status?: string;
  comparison_reason?: string;
  baseline_cost?: number | null;
  candidate_cost?: number | null;
  improvement_percent?: number | null;
  candidate_index_used?: boolean;
  baseline_plan?: Record<string, unknown> | null;
  candidate_plan?: Record<string, unknown> | null;
  details?: Record<string, unknown>;
};

export type Run = {
  id: string;
  status: string;
  target_database: string;
  created_at: string;
  queries: Array<{
    id: string;
    sql: string;
    calls: number;
    total_exec_time_ms: number;
    mean_exec_time_ms: number;
    plan: Record<string, unknown> | null;
    candidates: Candidate[];
  }>;
};

const base = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  status: () =>
    request<{
      status: string;
      checks: Record<string, { status: string; detail: string }>;
    }>("/api/v1/status"),
  workload: (limit = 100) =>
    request<{ count: number; queries: QueryRow[] }>(
      `/api/v1/workload?limit=${limit}`,
    ),
  history: (limit = 20, offset = 0) =>
    request<{ total: number; runs: Run[] }>(
      `/api/v1/history?limit=${limit}&offset=${offset}`,
    ),
  run: (id: string) => request<Run>(`/api/v1/history/${id}`),
  benchmark: () => request<Record<string, any>>("/api/v1/benchmark"),
  analyze: (sql: string) =>
    request<{
      status: string;
      reason: string | null;
      plan?: Record<string, unknown>;
      candidates: Candidate[];
    }>("/api/v1/analyze", { method: "POST", body: JSON.stringify({ sql }) }),
  verify: (payload: { sql: string; table_name: string; columns: string[] }) =>
    request<Record<string, any>>("/api/v1/verify", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
