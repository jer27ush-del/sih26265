/** Thin fetch wrapper for the Django API. The Vite dev server proxies /api to the backend (see vite.config.ts). */
export const API_BASE = '/api';
const TOKEN_KEY = 'aicte-token';

export class ApiError extends Error {
  status: number;
  code: string;
  fields: Record<string, unknown>;

  constructor(message: string, status: number, code: string, fields: Record<string, unknown>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  form?: FormData;
  /** Send the stored token. Sign-in and the demo role list are sent without one, so a stale token cannot block them. */
  auth?: boolean;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, form, auth = true } = options;
  const headers: Record<string, string> = {};
  const token = auth ? getToken() : null;
  if (token) headers.Authorization = `Token ${token}`;
  let payload: BodyInit | undefined;
  if (form) {
    payload = form;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  const response = await fetch(`${API_BASE}${path}`, { method, headers, body: payload });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const info = (data ?? {}) as { message?: string; code?: string; fields?: Record<string, unknown> };
    throw new ApiError(info.message ?? `Request failed (${response.status}).`, response.status,
      info.code ?? 'error', info.fields ?? {});
  }
  return data as T;
}
