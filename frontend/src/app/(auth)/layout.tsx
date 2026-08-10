import TrajectoryMark from "@/components/trajectory-mark";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      <div className="flex items-center justify-center px-6 py-12">{children}</div>

      <aside className="hidden border-border border-l bg-muted/20 lg:flex lg:flex-col lg:justify-center lg:gap-8 lg:px-12">
        <div className="flex flex-col gap-3">
          <span className="font-mono text-muted-foreground text-xs uppercase tracking-widest">
            driftline
          </span>
          <p className="max-w-md text-foreground text-lg leading-relaxed">
            Run a visual-inertial estimator over a recorded sequence, then measure how far the
            estimate drifts from ground truth.
          </p>
          <p className="max-w-md text-muted-foreground text-sm leading-relaxed">
            Trajectories are scored against hardware-measured truth, so a parameter change is judged
            by its effect on error rather than by eye.
          </p>
        </div>

        <TrajectoryMark />
      </aside>
    </div>
  );
}
