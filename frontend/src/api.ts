// Cliente HTTP da API NexusData.
// Princípio de segurança: NENHUM segredo é embutido no bundle. O front só
// guarda o JWT do usuário (obtido no login) e o envia como Bearer.

const BASE = import.meta.env.VITE_API_BASE ?? "";

export type Role = "admin" | "user";
export type JobStatus = "pending" | "processing" | "retrying" | "completed" | "failed";
export type DocType = "generic" | "invoice" | "contract" | "support_ticket";
export type Scope = "documents:write" | "documents:read" | "jobs:read" | "webhooks:write";
export type WebhookEvent = "job.completed" | "job.failed";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}
export interface Identity {
  user_id: string | null;
  tenant_id: string;
  role: Role;
  auth_method: string;
  scopes: string[];
}
export interface JobView {
  id: string;
  document_id: string;
  status: JobStatus;
  attempts: number;
  max_attempts: number;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}
export interface IngestResult {
  job_id: string;
  document_id: string;
  status: JobStatus;
  idempotent_replay: boolean;
}
export interface ApiKeyView {
  id: string;
  name: string;
  prefix: string;
  scopes: Scope[];
  is_active: boolean;
  last_used_at: string | null;
  expires_at: string | null;
}
export interface CreatedApiKey extends ApiKeyView {
  full_key: string;
}
export interface WebhookView {
  id: string;
  url: string;
  events: WebhookEvent[];
  is_active: boolean;
}
export interface RegisteredWebhook {
  id: string;
  url: string;
  events: WebhookEvent[];
  secret: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

const TOKEN_KEY = "nexus.tokens";

export const tokenStore = {
  get(): TokenPair | null {
    const raw = localStorage.getItem(TOKEN_KEY);
    return raw ? (JSON.parse(raw) as TokenPair) : null;
  },
  set(t: TokenPair) {
    localStorage.setItem(TOKEN_KEY, JSON.stringify(t));
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
  },
};

async function parseError(resp: Response): Promise<never> {
  let code = "error";
  let message = resp.statusText;
  try {
    const body = await resp.json();
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
    }
  } catch {
    /* corpo não-JSON */
  }
  throw new ApiError(resp.status, code, message);
}

async function refreshTokens(): Promise<boolean> {
  const tokens = tokenStore.get();
  if (!tokens) return false;
  const resp = await fetch(`${BASE}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  });
  if (!resp.ok) {
    tokenStore.clear();
    return false;
  }
  tokenStore.set((await resp.json()) as TokenPair);
  return true;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  auth?: boolean;
  _retried?: boolean;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { ...opts.headers };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.auth !== false) {
    const tokens = tokenStore.get();
    if (tokens) headers["Authorization"] = `Bearer ${tokens.access_token}`;
  }
  const resp = await fetch(`${BASE}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  // 401 → tenta refresh transparente uma única vez.
  if (resp.status === 401 && opts.auth !== false && !opts._retried) {
    if (await refreshTokens()) {
      return request<T>(path, { ...opts, _retried: true });
    }
  }
  if (!resp.ok) await parseError(resp);
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const api = {
  register: (data: {
    tenant_name: string;
    tenant_slug: string;
    admin_email: string;
    admin_password: string;
  }) => request("/api/v1/auth/register", { method: "POST", body: data, auth: false }),

  login: (email: string, password: string) =>
    request<TokenPair>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    }),

  me: () => request<Identity>("/api/v1/auth/me"),

  ingest: (
    body: { doc_type: DocType; filename?: string | null; raw_payload?: unknown },
    idempotencyKey?: string,
  ) =>
    request<IngestResult>("/api/v1/documents/process", {
      method: "POST",
      body,
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    }),

  jobs: (status?: JobStatus) =>
    request<JobView[]>(`/api/v1/jobs${status ? `?status=${status}` : ""}`),
  job: (id: string) => request<JobView>(`/api/v1/jobs/${id}`),

  apiKeys: () => request<ApiKeyView[]>("/api/v1/api-keys"),
  createApiKey: (name: string, scopes: Scope[]) =>
    request<CreatedApiKey>("/api/v1/api-keys", { method: "POST", body: { name, scopes } }),
  revokeApiKey: (id: string) =>
    request<void>(`/api/v1/api-keys/${id}`, { method: "DELETE" }),

  webhooks: () => request<WebhookView[]>("/api/v1/webhooks"),
  createWebhook: (url: string, events: WebhookEvent[]) =>
    request<RegisteredWebhook>("/api/v1/webhooks", { method: "POST", body: { url, events } }),
  deleteWebhook: (id: string) =>
    request<void>(`/api/v1/webhooks/${id}`, { method: "DELETE" }),
};

export function jobsSocketUrl(token: string): string {
  const base = BASE || window.location.origin;
  const url = new URL(base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/api/v1/ws/jobs";
  url.search = `?token=${encodeURIComponent(token)}`;
  return url.toString();
}
