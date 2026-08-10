"use client";

import Link from "next/link";
import { type FC, useCallback, useEffect, useMemo, useState } from "react";
import AppTopbar from "@/components/app-topbar";
import ErrorInspector from "@/components/runs/error-inspector";
import MetricsPanel from "@/components/runs/metrics-panel";
import RunStatusBadge from "@/components/runs/run-status-badge";
import TrackingView from "@/components/runs/tracking-view";
import { ErrorState, LoadingRows } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import TrajectoryViewer, { type TrajectoryPath } from "@/components/viewer/trajectory-viewer";
import { API_BASE, ApiError, api } from "@/lib/api";
import { formatCount, formatMetres, progressPercent, shortHash } from "@/lib/format";
import type {
  GroundTruthResponse,
  MetricsResponse,
  PoseErrorsResponse,
  Run,
  RunProgress,
  TrajectoryResponse,
} from "@/lib/types";

const ESTIMATE_FALLBACK = "#8b7fe8";
const TRUTH_FALLBACK = "#b9bec7";
// truth runs at six times the frame rate, so the drawn line is continuous well before every
// pose is sent
const TRUTH_STRIDE = 4;

const Stat: FC<{ label: string; value: string; hint?: string }> = ({ label, value, hint }) => (
  <div className="flex flex-col gap-0.5">
    <span className="text-muted-foreground text-xs">{label}</span>
    <span className="font-medium text-sm">{value}</span>
    {hint ? <span className="text-muted-foreground text-xs">{hint}</span> : null}
  </div>
);

const RunDetailScreen: FC<{ runId: string }> = ({ runId }) => {
  const [run, setRun] = useState<Run | null>(null);
  const [trajectory, setTrajectory] = useState<TrajectoryResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [errors, setErrors] = useState<PoseErrorsResponse | null>(null);
  const [truth, setTruth] = useState<GroundTruthResponse | null>(null);
  const [selectedPose, setSelectedPose] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);

  /**
   * Load the scores first, because they decide what the viewer should draw.
   *
   * A scored run gets the aligned estimate overlaid on truth, which is the only overlay that
   * means anything: unaligned, the two sit in different frames at different scales. An
   * unscored run gets the raw estimate on its own, and says so.
   */
  const loadResults = useCallback(async () => {
    let scored: MetricsResponse | null = null;
    try {
      scored = await api.get<MetricsResponse>(`/api/runs/${runId}/metrics`);
      setMetrics(scored);
    } catch {
      setMetrics(null);
    }

    const aligned = Boolean(scored?.metrics);
    try {
      const loaded = await api.get<TrajectoryResponse>(
        `/api/runs/${runId}/trajectory${aligned ? "?aligned=true" : ""}`,
      );
      setTrajectory(loaded);
    } catch {
      setTrajectory(null);
    }

    if (!aligned) {
      setErrors(null);
      setTruth(null);
      return;
    }

    try {
      setErrors(await api.get<PoseErrorsResponse>(`/api/runs/${runId}/errors`));
    } catch {
      setErrors(null);
    }
  }, [runId]);

  /**
   * Ground truth for the overlay, decimated.
   *
   * A room sequence carries over 16000 truth poses against a couple of thousand estimated
   * ones. Drawing every one costs a lot of geometry to render a line that is already
   * visually continuous at a fraction of the density.
   */
  const loadTruth = useCallback(async (datasetId: string) => {
    try {
      const loaded = await api.get<GroundTruthResponse>(
        `/api/datasets/${datasetId}/ground-truth?stride=${TRUTH_STRIDE}`,
      );
      setTruth(loaded.has_ground_truth && loaded.poses.length > 0 ? loaded : null);
    } catch {
      setTruth(null);
    }
  }, []);

  const load = useCallback(async () => {
    setError(null);
    try {
      const found = await api.get<Run>(`/api/runs/${runId}`);
      setRun(found);
      setLoading(false);
      void loadTruth(found.dataset_id);
      if (found.status === "done" || found.status === "failed") {
        await loadResults();
      } else {
        setStreaming(true);
      }
    } catch (caught) {
      setRun(null);
      setError(caught instanceof ApiError ? caught.message : "Could not load this run.");
      setLoading(false);
    }
  }, [runId, loadResults, loadTruth]);

  useEffect(() => {
    void load();
  }, [load]);

  const poseErrors = errors?.errors ?? [];

  /**
   * The paths the viewer draws.
   *
   * Truth is only overlaid once the estimate has been aligned onto it. Drawing both before
   * that would put two trajectories in different frames at different scales in the same
   * space, which invites reading the gap between them as error when it is mostly the
   * arbitrary frame the estimator started in.
   *
   * The error colours line up with the estimate pose for pose only when both came from the
   * same scored run, so they are attached only when the counts agree.
   */
  const viewerPaths = useMemo(() => {
    const poses = trajectory?.poses ?? [];
    const aligned = Boolean(trajectory?.aligned);
    const values = poseErrors.map((point) => point.trans_error);

    const paths: TrajectoryPath[] = [
      {
        poses,
        colorToken: "--estimate-path",
        fallbackColor: ESTIMATE_FALLBACK,
        label: "Estimate",
        errors: aligned && values.length === poses.length ? values : undefined,
      },
    ];

    if (aligned && truth?.poses.length) {
      paths.unshift({
        poses: truth.poses,
        colorToken: "--truth-path",
        fallbackColor: TRUTH_FALLBACK,
        label: "Ground truth",
        errors: undefined,
      });
    }
    return paths;
  }, [trajectory, truth, poseErrors]);

  const errorLegend = useMemo(() => {
    if (poseErrors.length === 0) return undefined;
    const worst = Math.max(...poseErrors.map((point) => point.trans_error));
    return `0 to ${formatMetres(worst)} off`;
  }, [poseErrors]);

  /**
   * Progress arrives over SSE rather than polling. The stream closes itself when the run
   * reaches a terminal status, and the scores and trajectory are fetched once at that point.
   *
   * This opens once per run id. The handler reads nothing from state, so it cannot capture a
   * stale run, and the effect does not re-run on every progress event.
   */
  useEffect(() => {
    if (!streaming) return;

    const source = new EventSource(`${API_BASE}/api/runs/${runId}/events`, {
      withCredentials: true,
    });

    source.onmessage = (event) => {
      const progress = JSON.parse(event.data) as RunProgress;
      setRun((current) =>
        current
          ? {
              ...current,
              status: progress.status,
              processed_frames: progress.frame,
              total_frames: progress.total,
              failure_reason: progress.failure_reason,
              failure_frame: progress.failure_frame,
            }
          : current,
      );

      if (progress.status === "done" || progress.status === "failed") {
        source.close();
        setStreaming(false);
        void loadResults();
      }
    };

    source.onerror = () => source.close();
    return () => source.close();
  }, [runId, streaming, loadResults]);

  if (loading) {
    return (
      <>
        <AppTopbar title="Run" />
        <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
          <div className="mx-auto w-full max-w-6xl">
            <LoadingRows rows={4} />
          </div>
        </main>
      </>
    );
  }

  if (error || !run) {
    return (
      <>
        <AppTopbar title="Run" />
        <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
          <div className="mx-auto w-full max-w-6xl">
            <ErrorState
              title="Could not load this run"
              message={error ?? "That run does not exist."}
              onRetry={() => void load()}
            />
          </div>
        </main>
      </>
    );
  }

  const { label, status, config, config_hash, processed_frames, total_frames } = run;
  const { failure_reason, failure_frame, dataset_id } = run;
  const percent = progressPercent(processed_frames, total_frames);
  const inFlight = status === "queued" || status === "running";

  return (
    <>
      <AppTopbar title={label ?? `Run ${shortHash(run.id)}`} />

      <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
          <section className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <RunStatusBadge status={status} />
              <span className="font-mono text-muted-foreground text-xs">
                {shortHash(config_hash)}
              </span>
              <Link
                href={`/app/datasets/${dataset_id}`}
                className="text-muted-foreground text-xs underline-offset-4 hover:underline"
              >
                View sequence
              </Link>
            </div>

            {inFlight ? (
              <div className="flex flex-col gap-2">
                <div className="flex items-baseline justify-between gap-4">
                  <span className="text-sm">
                    {status === "queued" ? "Waiting for the worker" : "Estimating"}
                  </span>
                  <span className="font-mono text-muted-foreground text-xs">
                    {formatCount(processed_frames)} / {formatCount(total_frames)}
                    {percent !== null ? ` (${percent}%)` : ""}
                  </span>
                </div>
                <div
                  className="h-1 w-full overflow-hidden rounded-full bg-border"
                  role="progressbar"
                  aria-valuenow={percent ?? 0}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className="h-full bg-foreground transition-[width] duration-300"
                    style={{ width: `${percent ?? 0}%` }}
                  />
                </div>
              </div>
            ) : null}

            {status === "failed" ? (
              <div
                role="alert"
                className="flex flex-col gap-1 rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3"
              >
                <span className="font-medium text-destructive text-sm">
                  Tracking failed
                  {failure_frame !== null ? ` at frame ${formatCount(failure_frame)}` : ""}
                </span>
                <p className="text-muted-foreground text-sm">{failure_reason}</p>
                <p className="text-muted-foreground text-xs">
                  The poses estimated before this frame are kept and drawn below.
                </p>
              </div>
            ) : null}

            <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
              <Stat label="Mode" value={config.mode} hint="visual only" />
              <Stat label="Max features" value={formatCount(config.max_features)} />
              <Stat
                label="Keyframe parallax"
                value={`${config.keyframe_parallax_px} px`}
                hint="motion needed to solve"
              />
              <Stat label="Poses" value={formatCount(trajectory?.total ?? processed_frames)} />
            </div>
          </section>

          {!inFlight ? (
            <section className="flex flex-col gap-3">
              <h2 className="font-medium text-sm">Accuracy</h2>
              <MetricsPanel metrics={metrics} status={status} />
            </section>
          ) : null}

          {/* the reserved height is for a drawn path; an empty state sizes to its own text */}
          <section
            className={`flex flex-col gap-2 ${
              inFlight || (trajectory?.poses.length ?? 0) > 0 ? "min-h-[380px]" : ""
            }`}
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-medium text-sm">
                {trajectory?.aligned ? "Estimate against ground truth" : "Estimated path"}
              </h2>
              <span className="text-muted-foreground text-xs">
                {trajectory?.aligned
                  ? "Aligned onto ground truth, so distances are in metres"
                  : trajectory?.scale_is_arbitrary
                    ? "Monocular, so distances have no absolute scale"
                    : null}
              </span>
            </div>
            {inFlight ? (
              <Skeleton className="min-h-[320px] flex-1 rounded-lg" />
            ) : (
              <TrajectoryViewer
                paths={viewerPaths}
                markerIndex={selectedPose}
                errorLegend={errorLegend}
                emptyMessage={
                  status === "failed"
                    ? "This run failed before it estimated any poses."
                    : "This run produced no poses."
                }
              />
            )}
          </section>

          {poseErrors.length > 0 ? (
            <section className="flex flex-col gap-3">
              <h2 className="font-medium text-sm">Error over the run</h2>
              <ErrorInspector
                errors={poseErrors}
                selected={selectedPose}
                onSelect={setSelectedPose}
              />
            </section>
          ) : null}

          {!inFlight && processed_frames > 0 ? (
            <section className="flex flex-col gap-2">
              <h2 className="font-medium text-sm">Feature tracking</h2>
              <TrackingView runId={runId} frameCount={processed_frames} />
            </section>
          ) : null}
        </div>
      </main>
    </>
  );
};

export default RunDetailScreen;
