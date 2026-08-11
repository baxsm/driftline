"use client";

import Link from "next/link";
import { type FC, useCallback, useEffect, useState } from "react";
import AppTopbar from "@/components/app-topbar";
import CompareErrorPlot from "@/components/compare/compare-error-plot";
import ConfigDiff from "@/components/compare/config-diff";
import MetricDeltas from "@/components/compare/metric-deltas";
import RunStatusBadge from "@/components/runs/run-status-badge";
import { EmptyState, ErrorState, LoadingRows } from "@/components/states";
import { Button } from "@/components/ui/button";
import TrajectoryViewer, { type TrajectoryPath } from "@/components/viewer/trajectory-viewer";
import { ApiError, api } from "@/lib/api";
import { formatCount, shortHash, truthWindowQuery } from "@/lib/format";
import type {
  CompareResponse,
  CompareSide,
  GroundTruthResponse,
  TrajectoryResponse,
} from "@/lib/types";

const A_FALLBACK = "#8b7fe8";
const B_FALLBACK = "#6fd08c";
const TRUTH_FALLBACK = "#b9bec7";
const TRUTH_STRIDE = 4;

interface CompareScreenProps {
  runA: string | null;
  runB: string | null;
}

/** A run needs a name in the table and the legend, and most runs are never given one. */
function sideLabel(side: CompareSide): string {
  return side.label ?? `Run ${shortHash(side.id)}`;
}

const SideSummary: FC<{ side: CompareSide; token: string }> = ({ side, token }) => (
  <div className="flex min-w-0 flex-1 flex-col gap-1.5">
    <div className="flex flex-wrap items-center gap-2">
      <span aria-hidden="true" className="h-0.5 w-4 rounded-full" style={{ background: token }} />
      <Link
        href={`/app/runs/${side.id}`}
        className="truncate font-medium text-sm underline-offset-4 hover:underline"
      >
        {sideLabel(side)}
      </Link>
      <RunStatusBadge status={side.status} />
    </div>
    <span className="font-mono text-muted-foreground text-xs">{shortHash(side.config_hash)}</span>
    {side.status === "failed" && side.failure_reason ? (
      <p className="text-destructive text-xs">
        {side.failure_reason}
        {side.failure_frame !== null ? ` (frame ${formatCount(side.failure_frame)})` : ""}
      </p>
    ) : null}
  </div>
);

/**
 * Two runs side by side.
 *
 * The trajectories are drawn in one viewer, which means both have to be in the same frame
 * first. Each is requested aligned, so both sit on ground truth and the gap between them is a
 * difference in the estimates rather than a difference in the arbitrary frame each started in.
 * A run that could not be aligned is drawn unaligned only if the other one could not be
 * either; mixing an aligned path with an unaligned one in the same space would invite reading
 * the distance between them as error.
 */
const CompareScreen: FC<CompareScreenProps> = ({ runA, runB }) => {
  const [data, setData] = useState<CompareResponse | null>(null);
  const [paths, setPaths] = useState<TrajectoryPath[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  /**
   * The three paths the viewer draws, fetched after the comparison itself.
   *
   * They are a few thousand poses each and are only needed once the pair is known to be
   * valid, so they load separately rather than holding the diff and the deltas behind them.
   */
  const loadPaths = useCallback(async (body: CompareResponse) => {
    async function trajectoryFor(id: string): Promise<TrajectoryResponse | null> {
      try {
        return await api.get<TrajectoryResponse>(`/api/runs/${id}/trajectory?aligned=true`);
      } catch {
        return null;
      }
    }

    const [a, b] = await Promise.all([trajectoryFor(body.a.id), trajectoryFor(body.b.id)]);

    const drawn: TrajectoryPath[] = [];
    // truth is only worth drawing when at least one estimate was actually put in its frame
    if (a?.aligned || b?.aligned) {
      try {
        // only the span the two estimates actually cover, so a short run is not drawn against
        // the whole recording and made to look like it followed all of it
        const window = truthWindowQuery([...(a?.poses ?? []), ...(b?.poses ?? [])]);
        const truth = await api.get<GroundTruthResponse>(
          `/api/datasets/${body.dataset_id}/ground-truth?stride=${TRUTH_STRIDE}${window}`,
        );
        if (truth.has_ground_truth && truth.poses.length > 0) {
          drawn.push({
            poses: truth.poses,
            colorToken: "--truth-path",
            fallbackColor: TRUTH_FALLBACK,
            label: "Ground truth",
          });
        }
      } catch {
        // the overlay is worth less than the two estimates, so a truth that will not load
        // leaves them drawn rather than emptying the viewer
      }
    }

    if (a?.poses.length) {
      drawn.push({
        poses: a.poses,
        colorToken: "--estimate-path",
        fallbackColor: A_FALLBACK,
        label: sideLabel(body.a),
      });
    }
    if (b?.poses.length) {
      drawn.push({
        poses: b.poses,
        colorToken: "--compare-path",
        fallbackColor: B_FALLBACK,
        label: sideLabel(body.b),
      });
    }
    setPaths(drawn);
  }, []);

  const load = useCallback(async () => {
    if (!runA || !runB) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const body = await api.get<CompareResponse>(
        `/api/compare?run_a=${encodeURIComponent(runA)}&run_b=${encodeURIComponent(runB)}`,
      );
      setData(body);
      void loadPaths(body);
    } catch (caught) {
      setData(null);
      setPaths([]);
      setError(caught instanceof ApiError ? caught.message : "Could not load this comparison.");
    } finally {
      setLoading(false);
    }
  }, [runA, runB, loadPaths]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!runA || !runB) {
    return (
      <>
        <AppTopbar title="Compare" />
        <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
          <div className="mx-auto w-full max-w-5xl">
            <EmptyState
              title="Pick two runs to compare"
              action={
                <Button asChild size="sm">
                  <Link href="/app/runs">Go to runs</Link>
                </Button>
              }
            >
              <p>
                Select exactly two runs on the same sequence from the runs list. This screen puts
                their settings, their scores and their paths next to each other, which is what turns
                tuning into a decision rather than a guess.
              </p>
            </EmptyState>
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <AppTopbar title="Compare" />

      <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
          {loading ? (
            <LoadingRows rows={4} />
          ) : error || !data ? (
            <ErrorState
              title="Could not compare these runs"
              message={error ?? "One of these runs does not exist."}
              onRetry={() => void load()}
            />
          ) : (
            <>
              <section className="flex flex-col gap-4 sm:flex-row sm:gap-8">
                <SideSummary side={data.a} token="var(--estimate-path)" />
                <SideSummary side={data.b} token="var(--compare-path)" />
              </section>

              <section className="flex flex-col gap-3">
                <h2 className="font-medium text-sm">What changed</h2>
                <ConfigDiff
                  rows={data.config_diff}
                  labelA={sideLabel(data.a)}
                  labelB={sideLabel(data.b)}
                />
              </section>

              <section className="flex min-h-[380px] flex-col gap-2">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 className="font-medium text-sm">Both paths</h2>
                  <span className="text-muted-foreground text-xs">
                    {data.a.dataset_name ?? "the same sequence"}
                  </span>
                </div>
                <TrajectoryViewer
                  paths={paths}
                  emptyMessage="Neither of these runs produced a path to draw."
                />
              </section>

              <section className="flex flex-col gap-3">
                <h2 className="font-medium text-sm">Scores</h2>
                <MetricDeltas
                  rows={data.metric_deltas}
                  labelA={sideLabel(data.a)}
                  labelB={sideLabel(data.b)}
                  alignmentA={data.a.metrics?.alignment ?? null}
                  alignmentB={data.b.metrics?.alignment ?? null}
                />
              </section>

              {data.a.errors.length > 0 || data.b.errors.length > 0 ? (
                <section className="flex flex-col gap-3">
                  <h2 className="font-medium text-sm">Error over the run</h2>
                  <CompareErrorPlot
                    a={data.a.errors}
                    b={data.b.errors}
                    labelA={sideLabel(data.a)}
                    labelB={sideLabel(data.b)}
                    kind="translation"
                  />
                  <CompareErrorPlot
                    a={data.a.errors}
                    b={data.b.errors}
                    labelA={sideLabel(data.a)}
                    labelB={sideLabel(data.b)}
                    kind="rotation"
                  />
                </section>
              ) : null}
            </>
          )}
        </div>
      </main>
    </>
  );
};

export default CompareScreen;
