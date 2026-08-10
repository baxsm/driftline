"use client";

import { type FC, useMemo } from "react";
import ErrorPlot from "@/components/runs/error-plot";
import { formatCount, formatDegrees, formatMetres } from "@/lib/format";
import type { PoseErrorPoint } from "@/lib/types";

interface ErrorInspectorProps {
  errors: PoseErrorPoint[];
  selected: number | null;
  onSelect: (index: number) => void;
}

/**
 * The two error plots and the control that moves through them.
 *
 * The plots are drawn as SVG and are hidden from assistive technology, because a path
 * element cannot express "pose 84 of 300, 4.2 cm". The range input underneath carries that:
 * it is the same selection, it moves with arrow keys, and it reads out the value at the
 * current pose. Pointer users get the plot, keyboard and screen reader users get the slider,
 * and both drive the same state as the 3D marker.
 */
const ErrorInspector: FC<ErrorInspectorProps> = ({ errors, selected, onSelect }) => {
  const current = selected ?? 0;
  const point = errors[current];

  const worst = useMemo(() => {
    let index = 0;
    for (let i = 1; i < errors.length; i += 1) {
      if (errors[i].trans_error > errors[index].trans_error) index = i;
    }
    return index;
  }, [errors]);

  if (errors.length === 0) return null;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 md:grid-cols-2">
        <ErrorPlot errors={errors} selected={selected} onSelect={onSelect} kind="translation" />
        <ErrorPlot errors={errors} selected={selected} onSelect={onSelect} kind="rotation" />
      </div>

      <div className="flex flex-col gap-2">
        <input
          type="range"
          min={0}
          max={errors.length - 1}
          value={current}
          onChange={(event) => onSelect(Number(event.target.value))}
          aria-label="Pose"
          aria-valuetext={`Pose ${current + 1} of ${errors.length}, position error ${formatMetres(
            point.trans_error,
          )}, rotation error ${formatDegrees(point.rot_error)}`}
          className="w-full cursor-pointer accent-foreground"
        />
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs">
          <span className="text-muted-foreground">
            Pose {formatCount(current + 1)} of {formatCount(errors.length)}
          </span>
          <span className="font-mono tabular-nums">
            {formatMetres(point.trans_error)} · {formatDegrees(point.rot_error)}
          </span>
          <button
            type="button"
            onClick={() => onSelect(worst)}
            className="ml-auto cursor-pointer text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            Jump to worst pose
          </button>
        </div>
      </div>
    </div>
  );
};

export default ErrorInspector;
