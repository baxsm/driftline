"use client";

import { Check, Minus } from "lucide-react";
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
  <ul data-testid="dataset-list" className="divide-y divide-border rounded-lg border border-border">
    {datasets.map((dataset) => {
      const { id, name, source, frame_count, imu_sample_count } = dataset;
      const { duration_seconds, has_ground_truth, camera_model, created_at } = dataset;

      return (
        <li key={id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
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

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-muted-foreground text-xs">
              <span>{formatCount(frame_count)} frames</span>
              <span>{formatCount(imu_sample_count)} IMU samples</span>
              <span>{formatDuration(duration_seconds)}</span>
              <span>{formatDate(created_at)}</span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-3">
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

            <Button
              variant="ghost"
              size="sm"
              onClick={() => onUnregister(dataset)}
              disabled={pendingId === id}
            >
              {pendingId === id ? "Removing" : "Unregister"}
            </Button>
          </div>
        </li>
      );
    })}
  </ul>
);

export default DatasetList;
