import type { FC } from "react";

/**
 * A small illustration of the product's core idea: one path is truth, the other drifts away
 * from it and is coloured by how far off it is. The curves are generated here rather than
 * traced from a real run, so this is a diagram, not a screenshot standing in for data.
 */

const WIDTH = 460;
const HEIGHT = 260;
const SAMPLES = 220;

function truthPoint(t: number): [number, number] {
  const angle = t * Math.PI * 2;
  return [
    WIDTH / 2 + Math.cos(angle) * 150 + Math.cos(angle * 2) * 18,
    HEIGHT / 2 + Math.sin(angle) * 78 - Math.sin(angle * 3) * 10,
  ];
}

function toPath(points: Array<[number, number]>): string {
  return points
    .map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`)
    .join(" ");
}

const truth: Array<[number, number]> = [];
const estimate: Array<[number, number]> = [];

for (let index = 0; index <= SAMPLES; index += 1) {
  const t = index / SAMPLES;
  const [x, y] = truthPoint(t);
  truth.push([x, y]);
  // error grows along the path, which is what unbounded drift looks like
  const drift = t * t * 26;
  estimate.push([x + drift * 0.9 + Math.sin(t * 9) * drift * 0.2, y - drift * 0.55]);
}

const TrajectoryMark: FC = () => (
  <figure className="flex flex-col gap-3">
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="h-auto w-full max-w-md"
      role="img"
      aria-label="An estimated trajectory drifting away from a ground truth path"
    >
      <defs>
        <linearGradient id="drift-ramp" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--color-error-low)" />
          <stop offset="100%" stopColor="var(--color-error-high)" />
        </linearGradient>
      </defs>

      <path
        d={toPath(truth)}
        fill="none"
        stroke="var(--color-truth-path)"
        strokeOpacity="0.7"
        strokeWidth="1.5"
        strokeDasharray="4 4"
      />
      <path
        d={toPath(estimate)}
        fill="none"
        stroke="url(#drift-ramp)"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>

    <figcaption className="flex items-center gap-4 text-muted-foreground text-xs">
      <span className="flex items-center gap-2">
        <span className="h-px w-6 border-truth-path border-t border-dashed" />
        ground truth
      </span>
      <span className="flex items-center gap-2">
        <span className="h-0.5 w-6 rounded-full bg-[linear-gradient(to_right,var(--color-error-low),var(--color-error-high))]" />
        estimate, coloured by error
      </span>
    </figcaption>
  </figure>
);

export default TrajectoryMark;
