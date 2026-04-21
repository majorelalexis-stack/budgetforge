const API_BASE = "";

export interface Project {
  id: number;
  name: string;
  api_key: string;
  budget_usd: number | null;
  alert_threshold_pct: number | null;
  action: "block" | "downgrade" | null;
  alert_email: string | null;
  reset_period: string;
  allowed_providers: string[];
  downgrade_chain: string[];
}

export interface UsageSummary {
  used_usd: number;
  budget_usd: number | null;
  remaining_usd: number;
  pct_used: number;
  calls: number;
  forecast_days: number | null;
}

export interface BudgetPayload {
  budget_usd: number;
  alert_threshold_pct: number;
  action: "block" | "downgrade";
  allowed_providers?: string[];
  downgrade_chain?: string[];
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: unknown }).detail;
    let message: string;
    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      message = first.msg ?? `HTTP ${res.status}`;
    } else {
      message = `HTTP ${res.status}`;
    }
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface ProviderStats {
  calls: number;
  cost_usd: number;
  tokens_in: number;
  tokens_out: number;
}

export interface UsageBreakdown {
  local_pct: number;
  cloud_pct: number;
  total_calls: number;
  providers: Record<string, ProviderStats>;
}

export interface AgentStats {
  calls: number;
  cost_usd: number;
}

export interface AgentBreakdown {
  agents: Record<string, AgentStats>;
  total_calls: number;
}

export interface UsageRecord {
  id: number;
  project_id: number;
  project_name: string;
  provider: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  agent: string | null;
  created_at: string;
}

export interface HistoryPage {
  items: UsageRecord[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  total_cost_usd: number;
}

export interface HistoryParams {
  page?: number;
  page_size?: number;
  project_id?: number | null;
  provider?: string | null;
  model?: string | null;
  date_from?: string | null;
  date_to?: string | null;
}

export interface DailySpend {
  date: string;
  spend: number;
}

export interface SiteSettings {
  smtp_host: string;
  smtp_port: number;
  smtp_user: string;
  smtp_password_set: boolean;
  alert_from_email: string;
}

export interface SiteSettingsUpdate {
  smtp_host?: string;
  smtp_port?: number;
  smtp_user?: string;
  smtp_password?: string;
  alert_from_email?: string;
}

export const api = {
  projects: {
    list: ()                           => req<Project[]>("/api/projects"),
    get:  (id: number)                 => req<Project>(`/api/projects/${id}`),
    create: (name: string)             => req<Project>("/api/projects", { method: "POST", body: JSON.stringify({ name }) }),
    delete: (id: number)               => req<void>(`/api/projects/${id}`, { method: "DELETE" }),
    setBudget: (id: number, b: BudgetPayload) =>
      req<Project>(`/api/projects/${id}/budget`, { method: "PUT", body: JSON.stringify(b) }),
    usage:     (id: number)            => req<UsageSummary>(`/api/projects/${id}/usage`),
    breakdown: (id: number)            => req<UsageBreakdown>(`/api/projects/${id}/usage/breakdown`),
    dailyUsage: (id: number)           => req<DailySpend[]>(`/api/projects/${id}/usage/daily`),
    rotateKey: (id: number)            => req<Project>(`/api/projects/${id}/rotate-key`, { method: "POST" }),
    agents:    (id: number)            => req<AgentBreakdown>(`/api/projects/${id}/usage/agents`),
  },
  usage: {
    breakdown: () => req<UsageBreakdown>("/api/usage/breakdown"),
    daily: async (): Promise<DailySpend[]> => {
      const resp = await fetch(`${API_BASE}/api/usage/daily`);
      if (!resp.ok) throw new Error("Failed to fetch daily usage");
      return resp.json();
    },
    exportUrl: (params: { format: "csv" | "json"; project_id?: number }) => {
      const qs = new URLSearchParams({ format: params.format });
      if (params.project_id != null) qs.set("project_id", String(params.project_id));
      return `${API_BASE}/api/usage/export?${qs.toString()}`;
    },
    history: (params: HistoryParams = {}) => {
      const qs = new URLSearchParams();
      if (params.page)       qs.set("page",       String(params.page));
      if (params.page_size)  qs.set("page_size",  String(params.page_size));
      if (params.project_id) qs.set("project_id", String(params.project_id));
      if (params.provider)   qs.set("provider",   params.provider);
      if (params.model)      qs.set("model",       params.model);
      if (params.date_from)  qs.set("date_from",  params.date_from);
      if (params.date_to)    qs.set("date_to",    params.date_to);
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return req<HistoryPage>(`/api/usage/history${suffix}`);
    },
  },
  health: () => req<{ status: string }>("/health"),
  models: () => req<{ providers: Record<string, string[]> }>("/api/models"),
  settings: {
    get:    ()                          => req<SiteSettings>("/api/settings"),
    update: (body: SiteSettingsUpdate) => req<SiteSettings>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  },
};
