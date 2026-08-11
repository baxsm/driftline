"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  type FC,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import { ApiError, api } from "@/lib/api";
import type { User } from "@/lib/types";

interface AuthValue {
  user: User | null;
  signIn: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

/**
 * Holds the signed in user, seeded by the server.
 *
 * There is no loading status any more, and that is the point. The provider used to fetch
 * `/api/auth/me` in an effect, so on every load the whole app knew nothing about the reader
 * until a round trip finished and had to render placeholders in the meantime. The session is
 * read on the server now and arrives with the markup, so `user` is correct in the first
 * render and there is no third state to design a screen for.
 */
export const AuthProvider: FC<{ user: User | null; children: ReactNode }> = ({
  user: initialUser,
  children,
}) => {
  const [user, setUser] = useState<User | null>(initialUser);
  const queryClient = useQueryClient();

  /*
   * Every cached row belongs to the account that fetched it, so the cache is dropped whenever
   * the account changes. Clearing only on sign out is not enough: signing in on a browser
   * that was already signed in as someone else leaves the previous reader's sequences and
   * runs in memory, and they render before the new request returns. Both directions are the
   * same event as far as the cache is concerned.
   */
  const authenticate = useCallback(
    async (path: string, email: string, password: string) => {
      const me = await api.post<User>(path, { email, password });
      queryClient.clear();
      setUser(me);
    },
    [queryClient],
  );

  const value = useMemo<AuthValue>(
    () => ({
      user,
      signIn: (email, password) => authenticate("/api/auth/login", email, password),
      register: (email, password) => authenticate("/api/auth/register", email, password),
      signOut: async () => {
        try {
          await api.post("/api/auth/logout");
        } catch (error) {
          // an expired session already achieves the goal, so only a real failure matters
          if (!(error instanceof ApiError) || error.status !== 401) throw error;
        }
        queryClient.clear();
        setUser(null);
      },
    }),
    [user, authenticate, queryClient],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
