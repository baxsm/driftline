"use client";

import Link from "next/link";
import { type FC, useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import AppTopbar from "@/components/app-topbar";
import RunList from "@/components/runs/run-list";
import { EmptyState, ErrorState, LoadingRows } from "@/components/states";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import type { RunSummary } from "@/lib/types";

/** Queued and running rows go stale on their own, so the list refreshes while any are live. */
const REFRESH_MS = 2000;

const RunsScreen: FC = () => {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const { runs: rows } = await api.get<{ runs: RunSummary[]; total: number }>("/api/runs");
      setRuns(rows);
      return rows;
    } catch (caught) {
      setRuns(null);
      setLoadError(caught instanceof ApiError ? caught.message : "Could not load your runs.");
      return null;
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * Polling stops as soon as nothing is in flight. The interval is rebuilt whenever the list
   * changes, so the check reads the runs it was created with rather than a stale closure.
   */
  useEffect(() => {
    const live = runs?.some((run) => run.status === "queued" || run.status === "running");
    if (!live) return;
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [runs, load]);

  async function handleDelete(run: RunSummary) {
    setPendingId(run.id);
    try {
      await api.delete(`/api/runs/${run.id}`);
      await load();
      toast.success("Run deleted", { description: "Its poses and artifacts were removed." });
    } catch (caught) {
      toast.error(caught instanceof ApiError ? caught.message : "Could not delete that run.");
    } finally {
      setPendingId(null);
    }
  }

  return (
    <>
      <AppTopbar title="Runs" />

      <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
          {loadError ? (
            <ErrorState
              title="Could not load runs"
              message={loadError}
              onRetry={() => void load()}
            />
          ) : runs === null ? (
            <LoadingRows />
          ) : runs.length === 0 ? (
            <EmptyState
              title="No runs yet"
              action={
                <Button asChild size="sm">
                  <Link href="/app/datasets">Go to sequences</Link>
                </Button>
              }
            >
              <p>
                A run estimates a trajectory from one sequence with one config. Open a registered
                sequence and queue one from there.
              </p>
            </EmptyState>
          ) : (
            <RunList runs={runs} onDelete={handleDelete} pendingId={pendingId} />
          )}
        </div>
      </main>
    </>
  );
};

export default RunsScreen;
