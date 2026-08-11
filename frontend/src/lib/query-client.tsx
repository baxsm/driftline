"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type FC, type ReactNode, useState } from "react";
import { ApiError } from "@/lib/api";

/**
 * The cache every screen reads through.
 *
 * The reason for it is what a run page did without one: it fetched the run, then its metrics,
 * then its trajectory, then truth, then the errors, one after another and again on every
 * visit. Going back to a run already read meant waiting for all of it a second time, and the
 * page rendered "this run produced no poses" in the gap.
 */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        /*
         * A run that has finished never changes, so data read once stays good for the session
         * and returning to it is instant. The queries that do go stale, the run lists and a
         * run still executing, set their own interval and override this.
         */
        staleTime: 60_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        /*
         * A 4xx is an answer, not a failure to get one. Retrying a 404 for a run that was
         * deleted, or a 401 after the session expired, only delays the message that says so.
         */
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
            return false;
          }
          return failureCount < 2;
        },
      },
    },
  });
}

let browserClient: QueryClient | undefined;

/**
 * One client per browser session, and a fresh one per request on the server.
 *
 * A module level client shared by every server request would leak one user's cached runs into
 * another's page. In the browser the opposite is wanted: the same client has to survive
 * navigation, or the cache it holds is thrown away on each route change.
 */
function getQueryClient(): QueryClient {
  if (typeof window === "undefined") return makeQueryClient();
  browserClient ??= makeQueryClient();
  return browserClient;
}

const QueryProvider: FC<{ children: ReactNode }> = ({ children }) => {
  // held in state rather than called inline, so a re-render never swaps the cache out
  const [client] = useState(getQueryClient);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
};

export default QueryProvider;
