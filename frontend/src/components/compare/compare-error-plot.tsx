"use client";

import { type FC, useMemo } from "react";
import { formatDegrees, formatMetres } from "@/lib/format";
import type { CompareErrorPoint } from "@/lib/types";

interface CompareErrorPlotProps {
  a: CompareErrorPoint[];
  b: CompareErrorPoint[];
  labelA: string;
  labelB: string;
  kind: "translation" | "rotation";
}

const VIEW_WIDTH = 1000;
const VIEW_HEIGHT = 200;
const PADDING_TOP = 12;
const PADDING_BOTTOM = 20;

/**
 * Both runs' error series on one pair of axes.
 *
 * Sharing the axes is the whole point, and it only works if both are drawn against the same
 * two ranges. The x axis spans the longer run and the y axis the larger error, so a run that
 * ended early stops partway across instead of being stretched to fill the width, which would
 * make it look like it drifted more slowly than it did.
 *
 * The x axis is seconds elapsed from each run's own first scored pose. Two runs over one
 * sequence can start at different frames, so their absolute timestamps do not share an origin
 * and plotting them against nanoseconds would offset one from the other by the gap between
 * their start frames rather than by anything either estimator did.
 */
const CompareErrorPlot: FC<CompareErrorPlotProps> = ({ a, b, labelA, labelB, kind }) => {
  const { pathA, pathB, peak, span } = useMemo(() => {
    const pick = (point: CompareErrorPoint) =>
      kind === "translation" ? point.trans_error : point.rot_error;
    const all = [...a, ...b];
    if (all.length === 0) return { pathA: "", pathB: "", peak: 0, span: 0 };

    const highest = Math.max(...all.map(pick));
    const longest = Math.max(...all.map((point) => point.t));
    const usableHeight = VIEW_HEIGHT - PADDING_TOP - PADDING_BOTTOM;
    // a flat series at zero, or a run of a single instant, would otherwise divide by zero
    const yScale = highest > 0 ? highest : 1;
    const xScale = longest > 0 ? longest : 1;

    function draw(points: CompareErrorPoint[]): string {
      if (points.length === 0) return "";
      const drawn = points.map((point) => {
        const x = (point.t / xScale) * VIEW_WIDTH;
        const y = PADDING_TOP + usableHeight * (1 - pick(point) / yScale);
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      });
      return `M ${drawn.join(" L ")}`;
    }

    return { pathA: draw(a), pathB: draw(b), peak: highest, span: longest };
  }, [a, b, kind]);

  const format = kind === "translation" ? formatMetres : formatDegrees;
  const label = kind === "translation" ? "Position error" : "Rotation error";

  if (a.length === 0 && b.length === 0) return null;

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-muted-foreground text-xs">{label}</span>
        <span className="font-mono text-muted-foreground text-xs tabular-nums">
          peak {format(peak)} over {span.toFixed(1)}s
        </span>
      </div>
      {/* hidden from assistive technology: the delta table above states every figure this
          draws, and a path element cannot be read as values */}
      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        preserveAspectRatio="none"
        className="h-28 w-full rounded-md border border-border bg-muted/10"
        role="presentation"
        aria-hidden="true"
      >
        <title>
          {label} for {labelA} and {labelB}
        </title>
        <path
          d={pathA}
          fill="none"
          stroke="var(--estimate-path)"
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
        />
        <path
          d={pathB}
          fill="none"
          stroke="var(--compare-path)"
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  );
};

export default CompareErrorPlot;
