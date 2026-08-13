"use client";

import { type FC, useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDegrees, formatMetres } from "@/lib/format";
import type { CompareErrorPoint } from "@/lib/types";

interface CompareErrorPlotProps {
  a: CompareErrorPoint[];
  b: CompareErrorPoint[];
  labelA: string;
  labelB: string;
  kind: "translation" | "rotation";
}

interface MergedPoint {
  t: number;
  a?: number;
  b?: number;
}

/**
 * Both runs' error series on one pair of axes.
 *
 * Sharing the axes is the whole point, and it only works if both are drawn against the same
 * two ranges. The x axis is a number axis spanning the longer run, so a run that ended early
 * stops partway across instead of being stretched to fill the width, which would make it look
 * like it drifted more slowly than it did. A category axis would do exactly that stretching,
 * which is why the domain is set explicitly.
 *
 * The x axis is seconds elapsed from each run's own first scored pose. Two runs over one
 * sequence can start at different frames, so their absolute timestamps do not share an origin
 * and plotting them against nanoseconds would offset one from the other by the gap between
 * their start frames rather than by anything either estimator did.
 */
const CompareErrorPlot: FC<CompareErrorPlotProps> = ({ a, b, labelA, labelB, kind }) => {
  const { data, peak, span } = useMemo(() => {
    const pick = (point: CompareErrorPoint) =>
      kind === "translation" ? point.trans_error : point.rot_error;
    const all = [...a, ...b];
    if (all.length === 0) return { data: [], peak: 0, span: 0 };

    /**
     * One row per distinct time, with each run's value on its own key.
     *
     * The two runs are scored at their own poses, so their time values rarely line up. Keying
     * by time puts both on one axis without pairing values that came from different moments.
     * Most rows therefore hold one run and leave the other null, which is why both lines set
     * `connectNulls`: without it each line breaks at every row belonging to the other run.
     */
    const byTime = new Map<number, MergedPoint>();
    function put(points: CompareErrorPoint[], key: "a" | "b") {
      for (const point of points) {
        const row = byTime.get(point.t) ?? { t: point.t };
        row[key] = pick(point);
        byTime.set(point.t, row);
      }
    }
    put(a, "a");
    put(b, "b");

    const merged = [...byTime.values()].sort((left, right) => left.t - right.t);
    return {
      data: merged,
      peak: Math.max(...all.map(pick)),
      span: Math.max(...all.map((point) => point.t)),
    };
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
      <div className="h-28 w-full rounded-md border border-border bg-muted/10">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 10, bottom: 4, left: 4 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              // the longer run sets the width; a short run must stop where it ended
              domain={[0, span > 0 ? span : 1]}
              tickFormatter={(value: number) => `${value.toFixed(0)}s`}
              stroke="var(--muted-foreground)"
              tick={{ fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              minTickGap={24}
            />
            <YAxis
              type="number"
              domain={[0, peak > 0 ? peak : 1]}
              width={44}
              tickFormatter={(value: number) => format(value)}
              stroke="var(--muted-foreground)"
              tick={{ fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--border)",
                borderRadius: "0.5rem",
                fontSize: "0.75rem",
              }}
              labelFormatter={(value) => `${Number(value).toFixed(2)}s`}
              formatter={(value, name) => [
                typeof value === "number" ? format(value) : String(value ?? ""),
                String(name ?? ""),
              ]}
            />
            <Line
              type="monotone"
              dataKey="a"
              name={labelA}
              stroke="var(--estimate-path)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="b"
              name={labelB}
              stroke="var(--compare-path)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default CompareErrorPlot;
