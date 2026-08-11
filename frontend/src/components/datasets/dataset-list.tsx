"use client";

import { Check, Loader2, Minus, Trash2 } from "lucide-react";
import Link from "next/link";
import type { FC } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatCount, formatDate, formatDuration, SOURCE_LABELS } from "@/lib/format";
import type { DatasetSummary } from "@/lib/types";

interface DatasetListProps {
  datasets: DatasetSummary[];
  onUnregister: (dataset: DatasetSummary) => void;
  pendingId: string | null;
}

/**
 * A divider separated list rather than a grid of cards, so rows scan vertically and nothing
 * is nested inside another bordered container.
 */
const DatasetList: FC<DatasetListProps> = ({ datasets, onUnregister, pendingId }) => (
  <ul
    data-testid="dataset-list"
    className="animate-rise-in divide-y divide-border overflow-hidden rounded-xl border border-border bg-card/40"
  >
    {datasets.map((dataset) => {
      const { id, name, source, frame_count, imu_sample_count } = dataset;
      const { duration_seconds, has_ground_truth, camera_model, created_at } = dataset;

      return (
        // stacks on a phone and sits on one line from sm up, so the actions never wrap into
        // the middle of the metadata
        <li
          key={id}
          className="flex flex-col gap-3 px-4 py-3 transition-colors duration-(--motion-quick) hover:bg-muted/40 sm:flex-row sm:items-center sm:gap-4"
        >
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <Link
                href={`/app/datasets/${id}`}
                className="truncate font-medium text-sm underline-offset-4 hover:underline"
              >
                {name}
              </Link>
              <Badge variant="outline">{SOURCE_LABELS[source]}</Badge>
              {camera_model ? (
                <span className="font-mono text-muted-foreground text-xs">{camera_model}</span>
              ) : null}
            </div>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground text-xs">
              <span className="whitespace-nowrap">{formatCount(frame_count)} frames</span>
              <span aria-hidden>/</span>
              <span className="whitespace-nowrap">{formatCount(imu_sample_count)} IMU</span>
              <span aria-hidden>/</span>
              <span className="whitespace-nowrap">{formatDuration(duration_seconds)}</span>
              <span aria-hidden>/</span>
              <span className="whitespace-nowrap">{formatDate(created_at)}</span>
            </div>
          </div>

          <div className="flex shrink-0 items-center justify-between gap-3 sm:justify-end">
            {has_ground_truth ? (
              <span className="flex items-center gap-1.5 text-foreground text-xs">
                <Check className="size-3.5" aria-hidden />
                Ground truth
              </span>
            ) : (
              <span
                className="flex items-center gap-1.5 text-muted-foreground text-xs"
                title="Runs on this sequence can be executed but never scored"
              >
                <Minus className="size-3.5" aria-hidden />
                No ground truth
              </span>
            )}

            {/* the files on disk are untouched, so this is reversible, but it still removes
                every run scored against the sequence and reads as destructive */}
            <Button
              variant="destructive"
              size="icon-sm"
              onClick={() => onUnregister(dataset)}
              disabled={pendingId === id}
              aria-label={`Unregister ${name}`}
              title="Unregister this sequence"
            >
              {pendingId === id ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <Trash2 aria-hidden />
              )}
            </Button>
          </div>
        </li>
      );
    })}
  </ul>
);

export default DatasetList;
