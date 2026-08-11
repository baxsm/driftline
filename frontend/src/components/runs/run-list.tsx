"use client";

import Link from "next/link";
import type { FC } from "react";
import RunStatusBadge from "@/components/runs/run-status-badge";
import { Button } from "@/components/ui/button";
import {
  ALIGNMENT_LABELS,
  formatCount,
  formatDate,
  formatMetres,
  progressPercent,
  shortHash,
} from "@/lib/format";
import type { RunSummary } from "@/lib/types";

interface RunListProps {
  runs: RunSummary[];
  onDelete: (run: RunSummary) => void;
  pendingId: string | null;
  /** The dataset name is redundant on a dataset page, where every run shares it. */
  showDataset?: boolean;
  /**
   * Ids picked for comparison. Selection is only offered when `onToggle` is given, so the
   * dataset page's list stays a plain list.
   */
  selected?: string[];
  onToggle?: (id: string) => void;
  /** Ids that cannot join the current selection, with the reason shown on the control. */
  disabledReason?: (run: RunSummary) => string | null;
}

const RunList: FC<RunListProps> = ({
  runs,
  onDelete,
  pendingId,
  showDataset = true,
  selected,
  onToggle,
  disabledReason,
}) => (
  <ul data-testid="run-list" className="divide-y divide-border rounded-lg border border-border">
    {runs.map((run) => {
      const { id, label, status, config_hash, processed_frames, total_frames } = run;
      const { dataset_name, created_at, failure_reason, ate_rmse, alignment } = run;
      const percent = progressPercent(processed_frames, total_frames);
      const isSelected = selected?.includes(id) ?? false;
      const blocked = disabledReason?.(run) ?? null;

      return (
        <li key={id} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
          {onToggle ? (
            <label
              className={`flex shrink-0 items-center gap-2 text-xs ${
                blocked && !isSelected
                  ? "cursor-not-allowed text-muted-foreground/60"
                  : "cursor-pointer text-muted-foreground"
              }`}
              title={blocked ?? undefined}
            >
              <input
                type="checkbox"
                checked={isSelected}
                disabled={Boolean(blocked) && !isSelected}
                onChange={() => onToggle(id)}
                aria-label={`Select ${label ?? `run ${shortHash(id)}`} to compare`}
                className="size-4 cursor-pointer accent-[var(--estimate-path)] disabled:cursor-not-allowed"
              />
              <span className="sm:hidden">Compare</span>
            </label>
          ) : null}

          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <Link
                href={`/app/runs/${id}`}
                className="truncate font-medium text-sm underline-offset-4 hover:underline"
              >
                {label ?? `Run ${shortHash(id)}`}
              </Link>
              <RunStatusBadge status={status} />
              <span className="font-mono text-muted-foreground text-xs">
                {shortHash(config_hash)}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground text-xs">
              {showDataset && dataset_name ? (
                <>
                  <span className="truncate">{dataset_name}</span>
                  <span aria-hidden>/</span>
                </>
              ) : null}
              <span className="whitespace-nowrap">
                {formatCount(processed_frames)} of {formatCount(total_frames)} frames
                {percent !== null && status === "running" ? ` (${percent}%)` : ""}
              </span>
              <span aria-hidden>/</span>
              <span className="whitespace-nowrap">{formatDate(created_at)}</span>
            </div>

            {status === "failed" && failure_reason ? (
              <p className="truncate text-destructive text-xs">{failure_reason}</p>
            ) : null}
          </div>

          {/*
            ATE carries its alignment mode. A Sim(3) figure had its scale fitted onto truth and
            an SE(3) one did not, so a column of bare numbers would invite ranking two runs that
            were never measuring the same thing.
          */}
          <div className="flex shrink-0 flex-col items-start gap-0.5 sm:items-end">
            {ate_rmse !== null ? (
              <>
                <span className="font-medium text-sm tabular-nums">{formatMetres(ate_rmse)}</span>
                <span className="text-muted-foreground text-xs">
                  ATE{alignment ? `, ${ALIGNMENT_LABELS[alignment]}` : ""}
                </span>
              </>
            ) : (
              <span className="text-muted-foreground text-xs">
                {status === "done" || status === "failed" ? "not scored" : "no score yet"}
              </span>
            )}
          </div>

          <div className="flex shrink-0 items-center justify-end gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onDelete(run)}
              disabled={pendingId === id}
            >
              {pendingId === id ? "Deleting" : "Delete"}
            </Button>
          </div>
        </li>
      );
    })}
  </ul>
);

export default RunList;
