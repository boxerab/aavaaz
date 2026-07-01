// SaaS management API (api-keys, usage, billing). Local default matches
// run_saas_api's port 8001, not the transcription server on 8000.
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface ApiOptions {
  token?: string | null;
  method?: string;
  body?: unknown;
}

export async function apiRequest<T>(
  path: string,
  options: ApiOptions = {}
): Promise<T> {
  const { token, method = "GET", body } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }

  return res.json();
}

// API Key types
export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used: string | null;
  expires_at: string | null;
}

export interface UsageRecord {
  date: string;
  audio_minutes: number;
  requests: number;
  cost_usd: number;
}

export interface UsageSummary {
  current_month: {
    audio_minutes: number;
    requests: number;
    cost_usd: number;
  };
  quota: {
    audio_minutes_limit: number;
    audio_minutes_used: number;
  };
  plan: string;
  daily_usage: UsageRecord[];
}

export interface Subscription {
  plan: string;
  status: string;
  current_period_end: string;
  cancel_at_period_end: boolean;
  price_per_minute: number;
  included_minutes: number;
}

// API Key management
export const apiKeys = {
  list: (token: string) =>
    apiRequest<ApiKey[]>("/v1/saas/api-keys", { token }),

  create: (token: string, name: string) =>
    apiRequest<{ key: ApiKey; secret: string }>("/v1/saas/api-keys", {
      token,
      method: "POST",
      body: { name },
    }),

  revoke: (token: string, keyId: string) =>
    apiRequest<void>(`/v1/saas/api-keys/${keyId}`, {
      token,
      method: "DELETE",
    }),
};

// Usage & billing
export const billing = {
  usage: (token: string) =>
    apiRequest<UsageSummary>("/v1/saas/usage", { token }),

  subscription: (token: string) =>
    apiRequest<Subscription>("/v1/saas/subscription", { token }),

  createCheckout: (token: string, plan: string) =>
    apiRequest<{ url: string }>("/v1/saas/checkout", {
      token,
      method: "POST",
      body: { plan },
    }),

  createPortalSession: (token: string) =>
    apiRequest<{ url: string }>("/v1/saas/billing-portal", {
      token,
      method: "POST",
    }),
};

// Transcription history
export interface TranscriptJob {
  id: string;
  filename: string;
  status: "pending" | "processing" | "completed" | "failed";
  duration_seconds: number;
  language: string;
  created_at: string;
  completed_at: string | null;
}

export const transcripts = {
  list: (token: string) =>
    apiRequest<TranscriptJob[]>("/v1/saas/transcripts", { token }),

  get: (token: string, id: string) =>
    apiRequest<TranscriptJob & { text: string }>(`/v1/saas/transcripts/${id}`, {
      token,
    }),
};
