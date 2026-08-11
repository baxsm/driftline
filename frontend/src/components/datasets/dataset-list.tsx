"use client";

import { Check, Loader2, Minus, Trash2 } from "lucide-react";
import type { FC } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import RowLink from "@/components/ui/row-link";
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
    className="stagger-rows divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface-panel"
  >
    {datasets.map((dataset) => {
      const { id, name, source, frame_count, imu_sample_count } = dataset;
      const { duration_seconds, has_ground_truth, camera_model, created_at } = dataset;

      return (
        // stacks on a phone and sits on one line from sm up, so the actions never wrap into
        // the middle of the metadata
        <li key={id}>
          <RowLink
            href={`/app/datasets/${id}`}
            label={name}
            className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:gap-4"
          >
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate font-medium text-sm">{name}</span>
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

            {/*
            The status and the destructive action are separated by a divider rather than sat
            next to each other. Reading left to right they were a tick and then a bin at the
            same weight, which made the tick look like a control.
          */}
            <div className="relative z-10 flex shrink-0 items-center justify-between gap-3 sm:justify-end">
              {has_ground_truth ? (
                <Badge variant="success">
                  <Check aria-hidden />
                  Ground truth
                </Badge>
              ) : (
                <Badge
                  variant="muted"
                  title="Runs on this sequence can be executed but never scored"
                >
                  <Minus aria-hidden />
                  No ground truth
                </Badge>
              )}

              <span aria-hidden className="hidden h-5 w-px bg-border sm:block" />

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
          </RowLink>
        </li>
      );
    })}
  </ul>
);

export default DatasetList;
