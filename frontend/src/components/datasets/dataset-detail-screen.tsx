"use client";

import { type FC, useState } from "react";
import { toast } from "sonner";
import AppTopbar from "@/components/app-topbar";
import CalibrationPanel from "@/components/datasets/calibration-panel";
import SequencePath from "@/components/datasets/sequence-path";
import RunConfigForm from "@/components/runs/run-config-form";
import RunList from "@/components/runs/run-list";
import { EmptyState, ErrorState, LoadingRows } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import Panel from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import TrajectoryViewer from "@/components/viewer/trajectory-viewer";
import { ApiError, api } from "@/lib/api";
import { formatCount, formatDuration, formatRate, SOURCE_LABELS } from "@/lib/format";
import { useDataset, useGroundTruth, useInvalidateRuns, useRuns } from "@/lib/queries";
import type { EstimatorConfig, Run, RunSummary } from "@/lib/types";

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
  const [pendingRunId, setPendingRunId] = useState<string | null>(null);
  const invalidateRuns = useInvalidateRuns();

  /**
   * The calibration and counts render as soon as the dataset row arrives. The thousands of
   * truth poses are a separate query, so they never hold the rest of the page on a skeleton,
   * and the viewer shows its own pending state until they land.
   */
  const datasetQuery = useDataset(datasetId);
  const dataset = datasetQuery.data ?? null;

  const truthQuery = useGroundTruth(
    dataset?.has_ground_truth ? datasetId : undefined,
    VIEWER_STRIDE,
  );
  const truth = dataset?.has_ground_truth
    ? (truthQuery.data ?? null)
    : { poses: [], stride: VIEWER_STRIDE, total: 0, has_ground_truth: false };

  const runsQuery = useRuns({ datasetId });
  const runs = runsQuery.data ?? null;

  async function handleQueue(config: EstimatorConfig, label: string) {
    const created = await api.post<Run>("/api/runs", {
      dataset_id: datasetId,
      config,
      ...(label ? { label } : {}),
    });
    invalidateRuns();
    toast.success("Run queued", {
      description: `${formatCount(created.total_frames)} frames to estimate.`,
    });
  }

  async function handleDeleteRun(run: RunSummary) {
    setPendingRunId(run.id);
    try {
      await api.delete(`/api/runs/${run.id}`);
      invalidateRuns();
      toast.success("Run deleted", { description: "Its poses and artifacts were removed." });
    } catch (caught) {
      toast.error(caught instanceof ApiError ? caught.message : "Could not delete that run.");
    } finally {
      setPendingRunId(null);
    }
  }

  if (datasetQuery.isPending) {
    return (
      <>
        <AppTopbar title="Sequence" parent={{ href: "/app/datasets", label: "Datasets" }} />
        <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
          <div className="mx-auto w-full max-w-6xl">
            <LoadingRows rows={4} />
          </div>
        </main>
      </>
    );
  }

  if (datasetQuery.isError || !dataset) {
    return (
      <>
        <AppTopbar title="Sequence" parent={{ href: "/app/datasets", label: "Datasets" }} />
        <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
          <div className="mx-auto w-full max-w-6xl">
            <ErrorState
              title="Could not load this sequence"
              message={
                datasetQuery.error instanceof ApiError
                  ? datasetQuery.error.message
                  : "That sequence does not exist."
              }
              onRetry={() => void datasetQuery.refetch()}
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
      <AppTopbar
        title={name}
        parent={{ href: "/app/datasets", label: "Datasets" }}
        action={<RunConfigForm frameCount={frame_count} onQueue={handleQueue} />}
      />

      <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
          <section className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{SOURCE_LABELS[source]}</Badge>
              {camera_model ? (
                <span className="font-mono text-muted-foreground text-xs">{camera_model}</span>
              ) : null}
              <SequencePath path={path} />
            </div>

            <div className="grid grid-cols-2 gap-x-6 gap-y-4 rounded-xl border border-border bg-surface-panel px-4 py-3.5 sm:grid-cols-4">
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

          {/* the reserved height is for a drawn path; an empty state sizes to its own text */}
          <Panel
            title="Ground truth path"
            aside={
              truth && truth.poses.length > 0
                ? `${formatCount(truth.poses.length)} of ${formatCount(truth.total)} poses drawn, every ${VIEWER_STRIDE}th`
                : undefined
            }
            className={has_ground_truth ? "min-h-[min(620px,calc(100svh-9rem))]" : ""}
            bodyClassName="flex min-h-0 flex-1 flex-col p-0"
          >
            {has_ground_truth && truth === null ? (
              <Skeleton className="min-h-[320px] flex-1 rounded-none" />
            ) : (
              <TrajectoryViewer
                paths={[
                  {
                    poses: truth?.poses ?? [],
                    colorToken: "--truth-path",
                    fallbackColor: "#b4b8c0",
                    label: "Ground truth",
                  },
                ]}
                emptyMessage={
                  has_ground_truth
                    ? "Ground truth is recorded but no poses were returned."
                    : "This sequence ships no ground truth, so there is no reference path to draw."
                }
              />
            )}
          </Panel>

          <Panel title="Runs" bodyClassName={runs && runs.length > 0 ? "p-0" : undefined}>
            {runsQuery.isError ? (
              <ErrorState
                title="Could not load runs"
                message={
                  runsQuery.error instanceof ApiError
                    ? runsQuery.error.message
                    : "Could not load runs for this sequence."
                }
                onRetry={() => void runsQuery.refetch()}
              />
            ) : runsQuery.isPending || runs === null ? (
              <LoadingRows rows={2} />
            ) : runs.length === 0 ? (
              <EmptyState title="No runs on this sequence">
                <p>
                  A run estimates a trajectory from these frames with one config. Queue one to see
                  where the estimate drifts.
                </p>
              </EmptyState>
            ) : (
              <RunList
                runs={runs}
                onDelete={handleDeleteRun}
                pendingId={pendingRunId}
                showDataset={false}
                flat
              />
            )}
          </Panel>

          <Panel title="Calibration">
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
          </Panel>
        </div>
      </main>
    </>
  );
};

export default DatasetDetailScreen;
