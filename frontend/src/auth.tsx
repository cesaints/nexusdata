import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, type Identity, tokenStore } from "./api";

interface AuthState {
  identity: Identity | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshIdentity: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshIdentity = useCallback(async () => {
    if (!tokenStore.get()) {
      setIdentity(null);
      return;
    }
    try {
      setIdentity(await api.me());
    } catch {
      tokenStore.clear();
      setIdentity(null);
    }
  }, []);

  useEffect(() => {
    void refreshIdentity().finally(() => setLoading(false));
  }, [refreshIdentity]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await api.login(email, password);
      tokenStore.set(tokens);
      await refreshIdentity();
    },
    [refreshIdentity],
  );

  const logout = useCallback(() => {
    tokenStore.clear();
    setIdentity(null);
  }, []);

  return (
    <AuthContext.Provider value={{ identity, loading, login, logout, refreshIdentity }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth fora do AuthProvider");
  return ctx;
}
