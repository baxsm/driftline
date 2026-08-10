"use client";

import Link from "next/link";
import { type FC, useCallback, useEffect, useState } from "react";
import AppTopbar from "@/components/app-topbar";
import RunStatusBadge from "@/components/runs/run-status-badge";
import TrackingView from "@/components/runs/tracking-view";
import { ErrorState, LoadingRows } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import TrajectoryViewer from "@/components/viewer/trajectory-viewer";
import { API_BASE, ApiError, api } from "@/lib/api";
import { formatCount, progressPercent, shortHash } from "@/lib/format";
import type { Run, RunProgress, TrajectoryResponse } from "@/lib/types";

const ESTIMATE_FALLBACK = "#8b7fe8";

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
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);

  const loadTrajectory = useCallback(async () => {
    try {
      const loaded = await api.get<TrajectoryResponse>(`/api/runs/${runId}/trajectory`);
      setTrajectory(loaded);
    } catch {
      setTrajectory(null);
    }
  }, [runId]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const found = await api.get<Run>(`/api/runs/${runId}`);
      setRun(found);
      setLoading(false);
      if (found.status === "done" || found.status === "failed") {
        await loadTrajectory();
      } else {
        setStreaming(true);
      }
    } catch (caught) {
      setRun(null);
      setError(caught instanceof ApiError ? caught.message : "Could not load this run.");
      setLoading(false);
    }
  }, [runId, loadTrajectory]);

  useEffect(() => {
    void load();
  }, [load]);

  /**
   * Progress arrives over SSE rather than polling. The stream closes itself when the run
   * reaches a terminal status, and the trajectory is fetched once at that point.
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
        void loadTrajectory();
      }
    };

    source.onerror = () => source.close();
    return () => source.close();
  }, [runId, streaming, loadTrajectory]);

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
              <Stat label="RANSAC threshold" value={`${config.ransac_threshold_px} px`} />
              <Stat label="Poses" value={formatCount(trajectory?.total ?? processed_frames)} />
            </div>
          </section>

          {/* the reserved height is for a drawn path; an empty state sizes to its own text */}
          <section
            className={`flex flex-col gap-2 ${
              inFlight || (trajectory?.poses.length ?? 0) > 0 ? "min-h-[380px]" : ""
            }`}
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-medium text-sm">Estimated path</h2>
              {trajectory?.scale_is_arbitrary ? (
                <span className="text-muted-foreground text-xs">
                  Monocular, so distances have no absolute scale
                </span>
              ) : null}
            </div>
            {inFlight ? (
              <Skeleton className="min-h-[320px] flex-1 rounded-lg" />
            ) : (
              <TrajectoryViewer
                paths={[
                  {
                    poses: trajectory?.poses ?? [],
                    colorToken: "--estimate-path",
                    fallbackColor: ESTIMATE_FALLBACK,
                    label: "Estimate",
                  },
                ]}
                emptyMessage={
                  status === "failed"
                    ? "This run failed before it estimated any poses."
                    : "This run produced no poses."
                }
              />
            )}
          </section>

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
