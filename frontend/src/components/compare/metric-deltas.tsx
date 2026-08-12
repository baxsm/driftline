"use client";

import type { FC } from "react";
import { ALIGNMENT_LABELS, formatDelta, formatMetric, METRIC_LABELS } from "@/lib/format";
import type { AlignmentMode, MetricDeltaRow } from "@/lib/types";

interface MetricDeltasProps {
  rows: MetricDeltaRow[];
  labelA: string;
  labelB: string;
  alignmentA: AlignmentMode | null;
  alignmentB: AlignmentMode | null;
}

/**
 * Both metric sets with a delta column.
 *
 * Every metric here is one where lower is better, so a negative delta means run B improved on
 * run A, and the column says "better" or "worse" rather than leaving a signed number to be
 * read the wrong way round.
 *
 * When the two runs were aligned differently the delta column is withheld entirely and the
 * reason is stated once above the table. A Sim(3) ATE has had its scale fitted onto truth and
 * an SE(3) one has not, so subtracting them produces a figure that looks like an improvement
 * and measures the alignment rather than the estimator.
 */
const MetricDeltas: FC<MetricDeltasProps> = ({ rows, labelA, labelB, alignmentA, alignmentB }) => {
  if (rows.length === 0) {
    return (
      <div className="px-1 py-2 text-muted-foreground text-sm">
        At least one of these runs was never scored, so there is nothing to compare. A run is scored
        only when its sequence has ground truth and enough of its poses line up with it.
      </div>
    );
  }

  const comparable = rows[0].comparable;

  return (
    <div className="flex flex-col gap-2">
      {!comparable && alignmentA && alignmentB ? (
        <p role="status" className="text-muted-foreground text-xs">
          These runs were aligned differently, {labelA} with {ALIGNMENT_LABELS[alignmentA]} and{" "}
          {labelB} with {ALIGNMENT_LABELS[alignmentB]}. Sim(3) fits scale onto ground truth and
          SE(3) does not, so the two sets of numbers are not measuring the same thing and no delta
          is shown.
        </p>
      ) : null}

      {/*
        the table keeps a minimum width and scrolls inside its own box rather than compressing
        to the viewport. Four columns squeezed into 375px wrap every heading onto three lines
        and clip the last one, which reads as broken rather than as scrollable.
      */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[34rem] text-sm">
          <thead>
            <tr className="border-border border-b text-left text-muted-foreground text-xs">
              <th scope="col" className="px-4 py-2 font-medium">
                Metric
              </th>
              <th scope="col" className="px-4 py-2 font-medium">
                <span className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="h-0.5 w-3 rounded-full bg-[var(--estimate-path)]"
                  />
                  {labelA}
                </span>
              </th>
              <th scope="col" className="px-4 py-2 font-medium">
                <span className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="h-0.5 w-3 rounded-full bg-[var(--compare-path)]"
                  />
                  {labelB}
                </span>
              </th>
              <th scope="col" className="px-4 py-2 font-medium">
                Change
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row) => {
              const { key, a, b, delta } = row;
              return (
                <tr key={key}>
                  <th scope="row" className="px-4 py-2 text-left font-normal text-muted-foreground">
                    {METRIC_LABELS[key] ?? key}
                  </th>
                  <td className="px-4 py-2 tabular-nums">{formatMetric(key, a)}</td>
                  <td className="px-4 py-2 tabular-nums">{formatMetric(key, b)}</td>
                  <td
                    className={`px-4 py-2 tabular-nums ${
                      delta === null
                        ? "text-muted-foreground"
                        : delta < 0
                          ? "text-[var(--error-low)]"
                          : "text-[var(--error-high)]"
                    }`}
                  >
                    {formatDelta(key, delta)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default MetricDeltas;
