"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FC, useEffect, useState } from "react";
import { toast } from "sonner";
import AppTopbar from "@/components/app-topbar";
import RunList from "@/components/runs/run-list";
import { EmptyState, ErrorState, LoadingRows } from "@/components/states";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { useInvalidateRuns, useRuns } from "@/lib/queries";
import type { RunSort, RunStatus, RunSummary } from "@/lib/types";

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
    /*
     * The selected option is a raised surface with the accent behind it, not a white pill.
     * Maximum contrast on a control that is only choosing a sort order pulled the eye away
     * from the scores, which are the reason to be on this screen.
     */
    className={`cursor-pointer rounded-md px-2.5 py-1 text-xs transition-colors duration-(--motion-quick) ${
      active
        ? "bg-surface-overlay font-medium text-foreground shadow-[inset_0_0_0_1px_var(--color-ring)]"
        : "text-muted-foreground hover:bg-surface-overlay/60 hover:text-foreground"
    }`}
  >
    {children}
  </button>
);

/**
 * A Toggle group behind its own label.
 *
 * The label used to sit inside the track with the options, styled almost the same, so "Sort"
 * and "Status" read as two more things that could be pressed. It is now outside the track and
 * typed as a field label: uppercase, smaller, letter spaced, and with no surface of its own.
 * The options keep the track, so what responds to the pointer is what looks like it will.
 */
const ToggleGroup: FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex items-center gap-2">
    <span className="font-medium text-[0.6875rem] text-muted-foreground/80 uppercase tracking-wider">
      {label}
    </span>
    <div className="flex items-center gap-0.5 rounded-lg border border-border bg-surface-raised/60 p-0.5">
      {children}
    </div>
  </div>
);

const RunsScreen: FC = () => {
  const router = useRouter();
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [sort, setSort] = useState<RunSort>("created");
  const [status, setStatus] = useState<RunStatus | "all">("all");
  const [selected, setSelected] = useState<string[]>([]);

  /**
   * Sorting and filtering happen in the database, not here.
   *
   * The list is paginated, so sorting the page that arrived would rank fifty rows out of
   * however many exist and present the best of those as the best overall. Each combination is
   * its own cache entry, so switching back to one already read is instant and the polling
   * only follows the list actually on screen.
   */
  const runsQuery = useRuns({ sort, status });
  const runs = runsQuery.data ?? null;
  const invalidateRuns = useInvalidateRuns();

  /*
   * A run that dropped out of the filtered list can no longer be compared from here, so it
   * leaves the selection rather than staying picked but invisible.
   */
  useEffect(() => {
    if (!runs) return;
    const visible = new Set(runs.map((row) => row.id));
    setSelected((current) => {
      const kept = current.filter((id) => visible.has(id));
      return kept.length === current.length ? current : kept;
    });
  }, [runs]);

  async function handleDelete(run: RunSummary) {
    setPendingId(run.id);
    try {
      await api.delete(`/api/runs/${run.id}`);
      setSelected((current) => current.filter((id) => id !== run.id));
      invalidateRuns();
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
              {/* the two groups need real air between them, or Sequence and Status read as
                  one strip of options */}
              <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
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

          {runsQuery.isError ? (
            <ErrorState
              title="Could not load runs"
              message={
                runsQuery.error instanceof ApiError
                  ? runsQuery.error.message
                  : "Could not load your runs."
              }
              onRetry={() => void runsQuery.refetch()}
            />
          ) : runsQuery.isPending ? (
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
