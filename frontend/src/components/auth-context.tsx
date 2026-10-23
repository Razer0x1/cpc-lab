"use client";
/** Auth + workspace context: token in localStorage, /auth/me profile, workspace switching. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, clearToken, getToken, setToken, setWorkspace, getWorkspace } from "@/lib/api";
import type { LoginResponse, Me, Workspace } from "@/lib/types";

type AuthState = {
  me: Me | null;
  workspaces: Workspace[];
  loading: boolean;
  login: (email: string, password: string) => Promise<Me>;
  logout: () => void;
  switchWorkspace: (id: string) => void;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);

  const loadProfile = useCallback(async () => {
    if (!getToken()) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      const list = await api.get<Workspace[]>("/api/v1/auth/workspaces");
      setWorkspaces(list);
      if (!getWorkspace() && list.length > 0) setWorkspace(list[0].id);
      const profile = await api.get<Me>("/api/v1/auth/me");
      setMe(profile);
    } catch {
      // 401 handled globally (redirect to /login); keep whatever state remains
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<LoginResponse>("/api/v1/auth/login", { email, password });
    setToken(res.access_token);
    const list = await api.get<Workspace[]>("/api/v1/auth/workspaces");
    setWorkspaces(list);
    if (list.length > 0) setWorkspace(list[0].id);
    const profile = await api.get<Me>("/api/v1/auth/me");
    setMe(profile);
    return profile;
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setMe(null);
    setWorkspaces([]);
    if (typeof window !== "undefined") window.location.href = "/login";
  }, []);

  const switchWorkspace = useCallback(
    (id: string) => {
      setWorkspace(id);
      void loadProfile();
    },
    [loadProfile]
  );

  const value = useMemo<AuthState>(
    () => ({ me, workspaces, loading, login, logout, switchWorkspace, refresh: loadProfile }),
    [me, workspaces, loading, login, logout, switchWorkspace, loadProfile]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
