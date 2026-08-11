"use client";

import type { FC } from "react";
import {
  ALIGNMENT_HINTS,
  ALIGNMENT_LABELS,
  formatCount,
  formatDegrees,
  formatMetres,
  formatScale,
  formatToleranceMs,
} from "@/lib/format";
import type { MetricsResponse, RunStatus } from "@/lib/types";

interface MetricsPanelProps {
  metrics: MetricsResponse | null;
  status: RunStatus;
}

const Figure: FC<{ label: string; value: string; hint?: string }> = ({ label, value, hint }) => (
  <div className="flex flex-col gap-0.5">
    <span className="text-muted-foreground text-xs">{label}</span>
    <span className="font-medium text-sm tabular-nums">{value}</span>
    {hint ? <span className="text-muted-foreground text-xs">{hint}</span> : null}
  </div>
);

const Note: FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="rounded-lg border border-border border-dashed bg-muted/10 px-4 py-3 text-muted-foreground text-sm">
    {children}
  </div>
);

/**
 * The scores, or an honest statement that there are none.
 *
 * Every branch that cannot show numbers says which case it is in. "No ground truth" and
 * "scored, and the error is zero" are completely different claims, and a panel that renders
 * zeros for the first is the failure this phase is most likely to ship.
 */
const MetricsPanel: FC<MetricsPanelProps> = ({ metrics, status }) => {
  if (status === "queued" || status === "running") {
    return <Note>Scores are computed when the run finishes.</Note>;
  }

  if (!metrics) {
    return <Note>Could not load the scores for this run.</Note>;
  }

  if (!metrics.has_ground_truth) {
    return (
      <Note>
        This sequence has no ground truth, so the estimate cannot be scored. The path below is the
        estimate on its own.
      </Note>
    );
  }

  if (!metrics.metrics) {
    return (
      <Note>
        This run was not scored. Too few estimated poses matched a ground truth timestamp to measure
        anything.
      </Note>
    );
  }

  const {
    ate_rmse,
    ate_mean,
    ate_median,
    ate_max,
    ate_rot_rmse,
    ate_rot_std,
    rpe_trans_rmse,
    rpe_rot_rmse,
    rpe_delta_frames,
    scale_error,
    alignment,
    aligned_pose_count,
    candidate_pose_count,
    association_tolerance_ns,
  } = metrics.metrics;

  // a score over a fraction of the run is a statement about that fraction, not the run
  const matchedRatio = candidate_pose_count > 0 ? aligned_pose_count / candidate_pose_count : 0;
  const partial = matchedRatio < 0.9;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="rounded-md border border-border px-2 py-0.5 font-medium text-xs">
          {ALIGNMENT_LABELS[alignment]} aligned
        </span>
        <span className="text-muted-foreground text-xs">{ALIGNMENT_HINTS[alignment]}</span>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
        <Figure
          label="ATE RMSE"
          value={formatMetres(ate_rmse)}
          hint="distance from truth, after alignment"
        />
        <Figure
          label="ATE median"
          value={formatMetres(ate_median)}
          hint={`mean ${formatMetres(ate_mean)}`}
        />
        <Figure label="ATE max" value={formatMetres(ate_max)} hint="worst single pose" />
        <Figure
          label="RPE translation"
          value={rpe_trans_rmse === null ? "not measured" : formatMetres(rpe_trans_rmse)}
          hint={
            rpe_trans_rmse === null
              ? "the run is shorter than one segment"
              : `drift over ${rpe_delta_frames} frames`
          }
        />
        <Figure
          label="RPE rotation"
          value={rpe_rot_rmse === null ? "not measured" : formatDegrees(rpe_rot_rmse)}
          hint={rpe_rot_rmse === null ? undefined : `over ${rpe_delta_frames} frames`}
        />
        <Figure
          label="Rotation offset"
          value={formatDegrees(ate_rot_rmse)}
          hint={`varies by ${formatDegrees(ate_rot_std)}`}
        />
        <Figure
          label="Scale"
          value={scale_error === null ? "measured" : formatScale(scale_error)}
          hint={
            scale_error === null
              ? "the estimator's own metres, never fitted to truth"
              : "monocular, so scale came from truth"
          }
        />
        <Figure
          label="Poses matched"
          value={`${formatCount(aligned_pose_count)} of ${formatCount(candidate_pose_count)}`}
          hint={`within ${formatToleranceMs(association_tolerance_ns)}`}
        />
      </div>

      {partial ? (
        <p role="status" className="text-muted-foreground text-xs">
          Only {Math.round(matchedRatio * 100)}% of the estimated poses matched a ground truth
          timestamp, so these numbers describe that part of the run rather than all of it.
        </p>
      ) : null}

      {alignment === "sim3" ? (
        <p className="text-muted-foreground text-xs">
          Scale was fitted onto ground truth, so this ATE cannot be compared against an SE(3) figure
          and it does not show scale drift.
        </p>
      ) : null}
    </div>
  );
};

export default MetricsPanel;
