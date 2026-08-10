"use client";

import { type FC, useCallback, useEffect, useState } from "react";
import AppTopbar from "@/components/app-topbar";
import CalibrationPanel from "@/components/datasets/calibration-panel";
import { EmptyState, ErrorState, LoadingRows } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import TrajectoryViewer from "@/components/viewer/trajectory-viewer";
import { ApiError, api } from "@/lib/api";
import { formatCount, formatDuration, formatRate, SOURCE_LABELS } from "@/lib/format";
import type { Dataset, GroundTruthResponse } from "@/lib/types";

/** 120Hz truth is far more than a line needs, so the viewer asks for every 4th pose. */
const VIEWER_STRIDE = 4;

const Stat: FC<{ label: string; value: string; hint?: string }> = ({ label, value, hint }) => (
  <div className="flex flex-col gap-0.5">
    <span className="text-muted-foreground text-xs">{label}</span>
    <span className="font-medium text-sm">{value}</span>
    {hint ? <span className="text-muted-foreground text-xs">{hint}</span> : null}
  </div>
);

const DatasetDetailScreen: FC<{ datasetId: string }> = ({ datasetId }) => {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [truth, setTruth] = useState<GroundTruthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  /**
   * The calibration and counts render as soon as the dataset row arrives. Fetching the
   * thousands of truth poses afterwards would hold the whole page on a skeleton, so the
   * trajectory loads on its own and the viewer shows its own pending state.
   */
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setTruth(null);
    try {
      const found = await api.get<Dataset>(`/api/datasets/${datasetId}`);
      setDataset(found);
      setLoading(false);

      if (found.has_ground_truth) {
        const loaded = await api.get<GroundTruthResponse>(
          `/api/datasets/${datasetId}/ground-truth?stride=${VIEWER_STRIDE}`,
        );
        setTruth(loaded);
      } else {
        setTruth({ poses: [], stride: VIEWER_STRIDE, total: 0, has_ground_truth: false });
      }
    } catch (caught) {
      setDataset(null);
      setError(caught instanceof ApiError ? caught.message : "Could not load this sequence.");
      setLoading(false);
    }
  }, [datasetId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <>
        <AppTopbar title="Sequence" />
        <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
          <div className="mx-auto w-full max-w-6xl">
            <LoadingRows rows={4} />
          </div>
        </main>
      </>
    );
  }

  if (error || !dataset) {
    return (
      <>
        <AppTopbar title="Sequence" />
        <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
          <div className="mx-auto w-full max-w-6xl">
            <ErrorState
              title="Could not load this sequence"
              message={error ?? "That sequence does not exist."}
              onRetry={() => void load()}
            />
          </div>
        </main>
      </>
    );
  }

  const { name, source, frame_count, imu_sample_count, duration_seconds } = dataset;
  const { has_ground_truth, camera_model, calibration, path } = dataset;
  const cameras = calibration.cameras ?? [];

  return (
    <>
      <AppTopbar title={name} />

      <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
          <section className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{SOURCE_LABELS[source]}</Badge>
              {camera_model ? (
                <span className="font-mono text-muted-foreground text-xs">{camera_model}</span>
              ) : null}
              <span className="truncate font-mono text-muted-foreground text-xs">{path}</span>
            </div>

            <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
              <Stat
                label="Frames"
                value={formatCount(frame_count)}
                hint={formatRate(frame_count, duration_seconds) ?? undefined}
              />
              <Stat
                label="IMU samples"
                value={formatCount(imu_sample_count)}
                hint={formatRate(imu_sample_count, duration_seconds) ?? undefined}
              />
              <Stat label="Duration" value={formatDuration(duration_seconds)} />
              <Stat
                label="Ground truth"
                value={has_ground_truth ? "Present" : "None"}
                hint={has_ground_truth ? "runs can be scored" : "runs cannot be scored"}
              />
            </div>
          </section>

          <section className="flex min-h-[380px] flex-col gap-2">
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="font-medium text-sm">Ground truth path</h2>
              {truth && truth.poses.length > 0 ? (
                <span className="text-muted-foreground text-xs">
                  {formatCount(truth.poses.length)} of {formatCount(truth.total)} poses drawn, every{" "}
                  {VIEWER_STRIDE}th
                </span>
              ) : null}
            </div>
            {has_ground_truth && truth === null ? (
              <Skeleton className="min-h-[320px] flex-1 rounded-lg" />
            ) : (
              <TrajectoryViewer
                poses={truth?.poses ?? []}
                emptyMessage={
                  has_ground_truth
                    ? "Ground truth is recorded but no poses were returned."
                    : "This sequence ships no ground truth, so there is no reference path to draw."
                }
              />
            )}
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="font-medium text-sm">Calibration</h2>
            {cameras.length === 0 && !calibration.imu ? (
              <EmptyState title="No calibration found">
                <p>
                  No <span className="font-mono">camchain.yaml</span> or{" "}
                  <span className="font-mono">imu_config.yaml</span> was found next to this
                  sequence.
                </p>
              </EmptyState>
            ) : (
              <CalibrationPanel cameras={cameras} imu={calibration.imu} />
            )}
          </section>
        </div>
      </main>
    </>
  );
};

export default DatasetDetailScreen;
