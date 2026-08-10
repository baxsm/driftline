"use client";

import Link from "next/link";
import type { FC } from "react";
import RunStatusBadge from "@/components/runs/run-status-badge";
import { Button } from "@/components/ui/button";
import { formatCount, formatDate, progressPercent, shortHash } from "@/lib/format";
import type { RunSummary } from "@/lib/types";

interface RunListProps {
  runs: RunSummary[];
  onDelete: (run: RunSummary) => void;
  pendingId: string | null;
  /** The dataset name is redundant on a dataset page, where every run shares it. */
  showDataset?: boolean;
}

const RunList: FC<RunListProps> = ({ runs, onDelete, pendingId, showDataset = true }) => (
  <ul data-testid="run-list" className="divide-y divide-border rounded-lg border border-border">
    {runs.map((run) => {
      const { id, label, status, config_hash, processed_frames, total_frames } = run;
      const { dataset_name, created_at, failure_reason } = run;
      const percent = progressPercent(processed_frames, total_frames);

      return (
        <li key={id} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
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
