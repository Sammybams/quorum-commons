import { clearSession, readSession, saveSession, type QuorumSession } from "./session";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
const clientGetCache = new Map<string, { expires_at: number; data: unknown }>();

type ApiGetOptions = {
  cachePolicy?: RequestCache;
  revalidateSeconds?: number;
  clientTtlMs?: number;
};

export async function apiGet<T>(path: string, options: ApiGetOptions = {}): Promise<T> {
  const cacheKey = buildClientCacheKey(path);
  if (typeof window !== "undefined" && options.clientTtlMs && cacheKey) {
    const cached = clientGetCache.get(cacheKey);
    if (cached && cached.expires_at > Date.now()) {
      return cached.data as T;
    }
  }

  const init: RequestInit & { next?: { revalidate: number } } = {
    headers: authHeaders(),
  };
  if (typeof window === "undefined") {
    init.next = { revalidate: options.revalidateSeconds ?? 30 };
  } else {
    init.cache = options.cachePolicy ?? "default";
  }

  const res = await fetchWithRefresh(`${API_BASE_URL}${path}`, init);
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  const data = (await res.json()) as T;
  if (typeof window !== "undefined" && options.clientTtlMs && cacheKey) {
    clientGetCache.set(cacheKey, { expires_at: Date.now() + options.clientTtlMs, data });
  }
  return data;
}

export async function apiPost<TResponse, TPayload>(path: string, payload: TPayload): Promise<TResponse> {
  const res = await fetchWithRefresh(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(await readError(res));
  }

  return res.json() as Promise<TResponse>;
}

export async function apiPatch<TResponse, TPayload>(path: string, payload: TPayload): Promise<TResponse> {
  const res = await fetchWithRefresh(`${API_BASE_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(await readError(res));
  }

  return res.json() as Promise<TResponse>;
}

export async function apiDelete(path: string): Promise<void> {
  const res = await fetchWithRefresh(`${API_BASE_URL}${path}`, {
    method: "DELETE",
    headers: authHeaders(),
  });

  if (!res.ok) {
    throw new Error(await readError(res));
  }
}

async function readError(res: Response) {
  const fallback = `Request failed: ${res.status} ${res.statusText}`;

  try {
    const data = await res.clone().json();
    if (typeof data?.detail === "string") {
      return data.detail;
    }
    if (Array.isArray(data?.detail)) {
      return data.detail.map((item: { msg?: string }) => item.msg || "Invalid field").join(", ");
    }
  } catch {
    const text = await res.text();
    return text || fallback;
  }

  return fallback;
}

async function fetchWithRefresh(input: string, init: RequestInit, allowRefresh = true): Promise<Response> {
  const res = await fetch(input, init);
  if (res.status !== 401 || !allowRefresh || typeof window === "undefined") {
    return res;
  }

  const refreshed = await refreshSession();
  if (!refreshed) {
    return res;
  }

  const nextHeaders = new Headers(init.headers || {});
  const auth = authHeaders();
  if (auth instanceof Headers) {
    auth.forEach((value, key) => nextHeaders.set(key, value));
  } else {
    Object.entries(auth).forEach(([key, value]) => {
      if (typeof value === "string") {
        nextHeaders.set(key, value);
      }
    });
  }

  return fetchWithRefresh(input, { ...init, headers: nextHeaders }, false);
}

async function refreshSession(): Promise<boolean> {
  const session = readSession();
  if (!session?.refresh_token) {
    clearSession();
    return false;
  }

  const res = await fetch(`${API_BASE_URL}/auth/refresh-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: session.refresh_token }),
  });

  if (!res.ok) {
    clearSession();
    return false;
  }

  const refreshed = (await res.json()) as QuorumSession;
  saveSession({
    ...session,
    ...refreshed,
    workspaces: refreshed.workspaces || session.workspaces,
  });
  return true;
}

function authHeaders(): HeadersInit {
  if (typeof window === "undefined") {
    return {};
  }

  try {
    const token = readSession()?.access_token;
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

function buildClientCacheKey(path: string) {
  if (typeof window === "undefined") {
    return null;
  }
  const token = readSession()?.access_token || "anon";
  return `${token}:${path}`;
}

export { API_BASE_URL };
