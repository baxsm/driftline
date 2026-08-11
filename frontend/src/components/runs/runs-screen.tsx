"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FC, useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import AppTopbar from "@/components/app-topbar";
import RunList from "@/components/runs/run-list";
import { EmptyState, ErrorState, LoadingRows } from "@/components/states";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import type { RunSort, RunStatus, RunSummary } from "@/lib/types";

/** Queued and running rows go stale on their own, so the list refreshes while any are live. */
const REFRESH_MS = 2000;

const SORTS: { value: RunSort; label: string }[] = [
  { value: "created", label: "Newest" },
  { value: "ate", label: "Best ATE" },
  { value: "dataset", label: "Sequence" },
];

const STATUSES: { value: RunStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "done", label: "Done" },
  { value: "running", label: "Running" },
  { value: "queued", label: "Queued" },
  { value: "failed", label: "Failed" },
];

/**
 * One option in a segmented control.
 *
 * The unselected options used to be bare text on the page background, which read as labels
 * rather than as things that could be pressed. The group now sits in its own track, so the
 * whole control is visible before anything is hovered.
 */
const Toggle: FC<{ active: boolean; onClick: () => void; children: React.ReactNode }> = ({
  active,
  onClick,
  children,
}) => (
  <button
    type="button"
    onClick={onClick}
    aria-pressed={active}
    className={`cursor-pointer rounded-md px-2.5 py-1 text-xs transition-colors duration-(--motion-quick) ${
      active
        ? "bg-foreground font-medium text-background"
        : "text-muted-foreground hover:bg-background/70 hover:text-foreground"
    }`}
  >
    {children}
  </button>
);

/** Holds a Toggle group, with the label sitting inside the same track as its options. */
const ToggleGroup: FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex items-center gap-1 rounded-lg border border-border bg-muted/30 p-0.5">
    <span className="px-1.5 text-muted-foreground text-xs">{label}</span>
    {children}
  </div>
);

const RunsScreen: FC = () => {
  const router = useRouter();
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [sort, setSort] = useState<RunSort>("created");
  const [status, setStatus] = useState<RunStatus | "all">("all");
  const [selected, setSelected] = useState<string[]>([]);

  /**
   * Sorting and filtering happen in the database, not here.
   *
   * The list is paginated, so sorting the page that arrived would rank fifty rows out of
   * however many exist and present the best of those as the best overall.
   */
  const load = useCallback(async () => {
    setLoadError(null);
    const query = new URLSearchParams({ sort });
    if (status !== "all") query.set("status", status);
    try {
      const { runs: rows } = await api.get<{ runs: RunSummary[]; total: number }>(
        `/api/runs?${query}`,
      );
      setRuns(rows);
      // a run that dropped out of the filtered list can no longer be compared from here, so
      // it leaves the selection rather than staying picked but invisible
      const visible = new Set(rows.map((row) => row.id));
      setSelected((current) => current.filter((id) => visible.has(id)));
    } catch (caught) {
      setRuns(null);
      setLoadError(caught instanceof ApiError ? caught.message : "Could not load your runs.");
    }
  }, [sort, status]);

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
      setSelected((current) => current.filter((id) => id !== run.id));
      await load();
      toast.success("Run deleted", { description: "Its poses and artifacts were removed." });
    } catch (caught) {
      toast.error(caught instanceof ApiError ? caught.message : "Could not delete that run.");
    } finally {
      setPendingId(null);
    }
  }

  function toggle(id: string) {
    setSelected((current) => {
      if (current.includes(id)) return current.filter((entry) => entry !== id);
      // exactly two, so picking a third replaces the older one rather than doing nothing,
      // which reads as the checkbox being broken
      return current.length < 2 ? [...current, id] : [current[1], id];
    });
  }

  const rows = runs ?? [];
  const firstPick = rows.find((run) => run.id === selected[0]);

  /**
   * Two runs on different sequences have no common ground truth, so their scores are not
   * comparable and the backend refuses the pair. Saying so on the control is better than
   * letting the selection be made and failing after the user has committed to it.
   */
  function blockedReason(run: RunSummary): string | null {
    if (!firstPick || run.id === firstPick.id) return null;
    if (run.dataset_id !== firstPick.dataset_id) {
      return "On a different sequence, so there is no common ground truth to compare against.";
    }
    return null;
  }

  return (
    <>
      <AppTopbar title="Runs" />

      <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
          {rows.length > 0 || status !== "all" ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <ToggleGroup label="Sort">
                  {SORTS.map((option) => (
                    <Toggle
                      key={option.value}
                      active={sort === option.value}
                      onClick={() => setSort(option.value)}
                    >
                      {option.label}
                    </Toggle>
                  ))}
                </ToggleGroup>
                <ToggleGroup label="Status">
                  {STATUSES.map((option) => (
                    <Toggle
                      key={option.value}
                      active={status === option.value}
                      onClick={() => setStatus(option.value)}
                    >
                      {option.label}
                    </Toggle>
                  ))}
                </ToggleGroup>
              </div>

              <div className="flex items-center gap-3">
                <span className="text-muted-foreground text-xs">
                  {selected.length === 0
                    ? "Pick two runs to compare"
                    : selected.length === 1
                      ? "Pick one more"
                      : "Two picked"}
                </span>
                <Button
                  size="sm"
                  disabled={selected.length !== 2}
                  onClick={() =>
                    router.push(`/app/compare?run_a=${selected[0]}&run_b=${selected[1]}`)
                  }
                >
                  Compare
                </Button>
              </div>
            </div>
          ) : null}

          {loadError ? (
            <ErrorState
              title="Could not load runs"
              message={loadError}
              onRetry={() => void load()}
            />
          ) : runs === null ? (
            <LoadingRows />
          ) : rows.length === 0 && status !== "all" ? (
            <EmptyState
              title={`No ${status} runs`}
              action={
                <Button variant="outline" size="sm" onClick={() => setStatus("all")}>
                  Show all runs
                </Button>
              }
            >
              <p>Other runs exist under a different status.</p>
            </EmptyState>
          ) : rows.length === 0 ? (
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
            <RunList
              runs={rows}
              onDelete={handleDelete}
              pendingId={pendingId}
              selected={selected}
              onToggle={toggle}
              disabledReason={blockedReason}
            />
          )}
        </div>
      </main>
    </>
  );
};

export default RunsScreen;
