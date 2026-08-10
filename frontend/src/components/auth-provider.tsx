"use client";

import {
  createContext,
  type FC,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { ApiError, api } from "@/lib/api";
import type { User } from "@/lib/types";

type AuthStatus = "loading" | "signed-in" | "signed-out";

interface AuthValue {
  user: User | null;
  status: AuthStatus;
  signIn: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export const AuthProvider: FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  useEffect(() => {
    let active = true;
    api
      .get<User>("/api/auth/me")
      .then((me) => {
        if (!active) return;
        setUser(me);
        setStatus("signed-in");
      })
      .catch(() => {
        if (!active) return;
        setUser(null);
        setStatus("signed-out");
      });
    return () => {
      active = false;
    };
  }, []);

  const authenticate = useCallback(async (path: string, email: string, password: string) => {
    const me = await api.post<User>(path, { email, password });
    setUser(me);
    setStatus("signed-in");
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      user,
      status,
      signIn: (email, password) => authenticate("/api/auth/login", email, password),
      register: (email, password) => authenticate("/api/auth/register", email, password),
      signOut: async () => {
        try {
          await api.post("/api/auth/logout");
        } catch (error) {
          // an expired session already achieves the goal, so only a real failure matters
          if (!(error instanceof ApiError) || error.status !== 401) throw error;
        }
        setUser(null);
        setStatus("signed-out");
      },
    }),
    [user, status, authenticate],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
