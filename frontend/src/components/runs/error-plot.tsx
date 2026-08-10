"use client";

import { type FC, useCallback, useMemo, useRef, useState } from "react";
import { formatDegrees, formatMetres } from "@/lib/format";
import type { PoseErrorPoint } from "@/lib/types";

interface ErrorPlotProps {
  errors: PoseErrorPoint[];
  /** Which pose is selected, as an index into `errors`. */
  selected: number | null;
  onSelect: (index: number) => void;
  kind: "translation" | "rotation";
}

const VIEW_WIDTH = 1000;
const VIEW_HEIGHT = 200;
const PADDING_TOP = 12;
const PADDING_BOTTOM = 20;

/**
 * Error against time, drawn as an area with a line on top.
 *
 * This is an SVG rather than a chart library. The plot has one series, shares its x axis
 * with the scrubber and the 3D marker, and needs a click anywhere on it to resolve to a
 * pose index. A chart library would be a dependency and a set of defaults to fight for a
 * shape this specific.
 *
 * The x axis is the pose index, not the timestamp. The poses being plotted are exactly the
 * ones that matched a truth pose, so they are already the run's own ordering, and spacing
 * them by time would leave gaps wherever a pose failed to match, which reads as missing data
 * rather than as an unmatched frame.
 */
const ErrorPlot: FC<ErrorPlotProps> = ({ errors, selected, onSelect, kind }) => {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hovered, setHovered] = useState<number | null>(null);

  const values = useMemo(
    () => errors.map((error) => (kind === "translation" ? error.trans_error : error.rot_error)),
    [errors, kind],
  );

  const { path, area, peak, floor } = useMemo(() => {
    if (values.length === 0) return { path: "", area: "", peak: 0, floor: 0 };
    const highest = Math.max(...values);
    const lowest = Math.min(...values);

    /**
     * The axis starts at zero unless the series barely moves.
     *
     * Rotation error after a position-only alignment is usually a large constant offset with
     * a small wobble on top. Drawn from zero that is a solid block at full height, which
     * reads as the error being at its maximum everywhere. When the variation is small
     * against the value, the axis starts at the lowest point instead, so what is shown is
     * the part that actually changes.
     */
    const flat = highest > 0 && highest - lowest < highest * 0.25;
    const base = flat ? lowest : 0;
    const span = highest - base;
    // a series with no variation at all would divide by zero and collapse onto the axis
    const scale = span > 0 ? span : 1;

    const stepX = values.length > 1 ? VIEW_WIDTH / (values.length - 1) : 0;
    const usableHeight = VIEW_HEIGHT - PADDING_TOP - PADDING_BOTTOM;

    const points = values.map((value, index) => {
      const x = values.length > 1 ? index * stepX : VIEW_WIDTH / 2;
      const y = PADDING_TOP + usableHeight * (1 - (value - base) / scale);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    });

    const baseline = VIEW_HEIGHT - PADDING_BOTTOM;
    return {
      path: `M ${points.join(" L ")}`,
      area: `M 0,${baseline} L ${points.join(" L ")} L ${VIEW_WIDTH},${baseline} Z`,
      peak: highest,
      floor: base,
    };
  }, [values]);

  const indexFromPointer = useCallback(
    (clientX: number): number | null => {
      const svg = svgRef.current;
      if (!svg || values.length === 0) return null;
      const { left, width } = svg.getBoundingClientRect();
      if (width === 0) return null;
      const ratio = Math.min(Math.max((clientX - left) / width, 0), 1);
      return Math.round(ratio * (values.length - 1));
    },
    [values.length],
  );

  if (errors.length === 0) return null;

  const active = hovered ?? selected;
  const activeValue = active !== null ? values[active] : undefined;
  const markerX =
    active !== null && values.length > 1 ? (active / (values.length - 1)) * VIEW_WIDTH : 0;

  const format = kind === "translation" ? formatMetres : formatDegrees;
  const label = kind === "translation" ? "Position error" : "Rotation error";

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-muted-foreground text-xs">{label}</span>
        <span className="font-mono text-muted-foreground text-xs tabular-nums">
          {activeValue !== undefined
            ? format(activeValue)
            : floor > 0
              ? `${format(floor)} to ${format(peak)}`
              : `peak ${format(peak)}`}
        </span>
      </div>
      {/* hidden from assistive technology on purpose: the range input in the inspector is
          the same selection and can state the value at the current pose, which a path
          element cannot */}
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        preserveAspectRatio="none"
        className="h-24 w-full cursor-pointer touch-none rounded-md border border-border bg-muted/10"
        role="presentation"
        aria-hidden="true"
        onPointerMove={(event) => setHovered(indexFromPointer(event.clientX))}
        onPointerLeave={() => setHovered(null)}
        onPointerDown={(event) => {
          const index = indexFromPointer(event.clientX);
          if (index !== null) onSelect(index);
        }}
      >
        <title>{label} over the run</title>
        <path d={area} fill="var(--error-high)" fillOpacity={0.12} />
        <path
          d={path}
          fill="none"
          stroke="var(--error-high)"
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
        />
        {active !== null ? (
          <line
            x1={markerX}
            x2={markerX}
            y1={PADDING_TOP - 6}
            y2={VIEW_HEIGHT - PADDING_BOTTOM}
            stroke="var(--foreground)"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
        ) : null}
      </svg>
    </div>
  );
};

export default ErrorPlot;
