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
import Panel from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
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
      <RunStatusBadge status={side.status} showDone />
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
   * Whether the trajectories are still arriving.
   *
   * The comparison itself resolves before them, so the screen is drawn while `paths` is still
   * empty. Without this the viewer reads that as "neither run produced a path", which is a
   * result, on runs that produced thousands of poses. Same distinction the run screen draws
   * with `resultsPending`.
   */
  const [pathsPending, setPathsPending] = useState(true);

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
    setPathsPending(true);
    setError(null);
    try {
      const body = await api.get<CompareResponse>(
        `/api/compare?run_a=${encodeURIComponent(runA)}&run_b=${encodeURIComponent(runB)}`,
      );
      setData(body);
      // deliberately not awaited: the diff and the deltas are worth showing before a few
      // thousand poses finish arriving. `pathsPending` is what holds the viewer until they do.
      void loadPaths(body).finally(() => setPathsPending(false));
    } catch (caught) {
      setData(null);
      setPaths([]);
      setPathsPending(false);
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
              <section className="flex animate-rise-in flex-col gap-4 rounded-xl border border-border bg-card/40 px-4 py-3.5 sm:flex-row sm:gap-8">
                <SideSummary side={data.a} token="var(--estimate-path)" />
                <SideSummary side={data.b} token="var(--compare-path)" />
              </section>

              <Panel title="What changed" bodyClassName="p-0">
                <ConfigDiff
                  rows={data.config_diff}
                  labelA={sideLabel(data.a)}
                  labelB={sideLabel(data.b)}
                />
              </Panel>

              <Panel
                title="Both paths"
                aside={data.a.dataset_name ?? "the same sequence"}
                className="min-h-[min(620px,calc(100svh-9rem))]"
                bodyClassName="flex min-h-0 flex-1 flex-col p-0"
              >
                {/* paths still in flight are loading, not absent */}
                {pathsPending ? (
                  <Skeleton className="min-h-[320px] flex-1 rounded-none" />
                ) : (
                  <TrajectoryViewer
                    paths={paths}
                    emptyMessage="Neither of these runs produced a path to draw."
                  />
                )}
              </Panel>

              <Panel title="Scores" bodyClassName="p-0">
                <MetricDeltas
                  rows={data.metric_deltas}
                  labelA={sideLabel(data.a)}
                  labelB={sideLabel(data.b)}
                  alignmentA={data.a.metrics?.alignment ?? null}
                  alignmentB={data.b.metrics?.alignment ?? null}
                />
              </Panel>

              {data.a.errors.length > 0 || data.b.errors.length > 0 ? (
                <Panel title="Error over the run" bodyClassName="flex flex-col gap-3">
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
                </Panel>
              ) : null}
            </>
          )}
        </div>
      </main>
    </>
  );
};

export default CompareScreen;
