/** Typed API client with auth + workspace headers and 401 handling. */

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

const TOKEN_KEY = "cpc_token";
const WORKSPACE_KEY = "cpc_workspace";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(WORKSPACE_KEY);
}
export function setWorkspace(id: string) {
  localStorage.setItem(WORKSPACE_KEY, id);
}
export function getWorkspace(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(WORKSPACE_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

/* ------------------------------------------------------------------ */
/* Connection state (real reachability, not navigator.onLine guessing) */
/* ------------------------------------------------------------------ */

export type ConnState = "online" | "offline";

const connListeners = new Set<(state: ConnState) => void>();
let connState: ConnState =
  typeof navigator !== "undefined" && navigator.onLine === false ? "offline" : "online";

export function isOffline(): boolean {
  return connState === "offline";
}
export function subscribeConnection(cb: (state: ConnState) => void): () => void {
  connListeners.add(cb);
  return () => {
    connListeners.delete(cb);
  };
}
function setConn(state: ConnState) {
  if (state === connState) return;
  connState = state;
  connListeners.forEach((cb) => cb(state));
}

if (typeof window !== "undefined") {
  window.addEventListener("offline", () => setConn("offline"));
  window.addEventListener("online", () => {
    // Optimistically mark reachable; the next request failure flips it back.
    setConn("online");
  });
}

/* ------------------------------------------------------------------ */
/* Read cache: last successful GET per path, served only when offline   */
/* ------------------------------------------------------------------ */

const CACHE_PREFIX = "cpc_cache:";
const CACHE_TTL_MS = 12 * 60 * 60 * 1000; // labeled "cached" in the UI banner

type CacheEntry = { t: number; d: unknown };

function cacheRead(path: string): CacheEntry | null {
  try {
    const raw = localStorage.getItem(CACHE_PREFIX + path);
    if (!raw) return null;
    const entry = JSON.parse(raw) as CacheEntry;
    if (!entry || typeof entry.t !== "number") return null;
    if (Date.now() - entry.t > CACHE_TTL_MS) return null;
    return entry;
  } catch {
    return null;
  }
}

function cacheWrite(path: string, data: unknown) {
  try {
    localStorage.setItem(CACHE_PREFIX + path, JSON.stringify({ t: Date.now(), d: data }));
  } catch {
    /* storage quota — cache is best-effort */
  }
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const ws = getWorkspace();
  if (ws) headers["X-Workspace-ID"] = ws;

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch (err) {
    // Network-level failure: backend unreachable or browser offline.
    setConn("offline");
    throw new ApiError(
      0,
      "Cannot reach the CPC Lab API — make sure the backend is running on :8000 (run 'CPC Lab (full stack)' from VS Code, F5) or check your connection."
    );
  }
  setConn("online");
  if (res.status === 401 && retry && typeof window !== "undefined") {
    clearToken();
    window.location.href = "/login";
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function download(path: string, filename: string): Promise<void> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const ws = getWorkspace();
  if (ws) headers["X-Workspace-ID"] = ws;
  const res = await fetch(`${API_URL}${path}`, { headers });
  if (!res.ok) throw new ApiError(res.status, "Download failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const api = {
  get: async <T>(path: string) => {
    try {
      const data = await request<T>(path);
      cacheWrite(path, data);
      return data;
    } catch (err) {
      // Offline fallback: serve the last successful response for this path.
      // The UI Banner labels the session as offline, so data is never presented as live.
      if (err instanceof ApiError && err.status === 0 && typeof window !== "undefined") {
        const cached = cacheRead(path);
        if (cached) return cached.d as T;
      }
      throw err;
    }
  },
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  download,
};

import { useEffect, useState, useCallback } from "react";

/** Minimal data hook with loading/error state and optional polling. */
export function useApi<T>(path: string | null, pollMs = 0): {
  data: T | null; error: string | null; loading: boolean; refresh: () => void;
} {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!path) return;
    let alive = true;
    setLoading(true);
    api
      .get<T>(path)
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [path, tick]);

  useEffect(() => {
    if (!path || !pollMs) return;
    const t = setInterval(refresh, pollMs);
    return () => clearInterval(t);
  }, [path, pollMs, refresh]);

  return { data, error, loading, refresh };
}

/** Connection state for UI (banner); reacts to api experience + browser events. */
export function useConnection(): { offline: boolean } {
  const [offline, setOfflineLocal] = useState(isOffline());
  useEffect(
    () =>
      subscribeConnection(() => {
        setOfflineLocal(isOffline());
      }),
    []
  );
  return { offline };
}

export function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v < 10 && i > 0 ? v.toFixed(2) : Math.round(v)} ${units[i]}`;
}

export function fmtNum(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(digits);
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
