import type { FC } from "react";
import { Badge } from "@/components/ui/badge";
import { RUN_STATUS_LABELS } from "@/lib/format";
import type { RunStatus } from "@/lib/types";

/**
 * Failed is the only status that gets the destructive treatment. Done stays neutral because a
 * finished run is not a success claim on its own: "done" means the estimator reached the last
 * frame, not that the trajectory is any good.
 */
const VARIANTS: Record<RunStatus, "default" | "secondary" | "destructive" | "outline"> = {
  queued: "outline",
  running: "secondary",
  done: "outline",
  failed: "destructive",
};

/**
 * A finished run is the normal case, so it carries no badge at all: in a list where most rows
 * are done, a "Done" chip on each one is noise that makes the two states worth noticing, the
 * failure and the run still going, harder to pick out. The score next to it already says the
 * run finished. `showDone` is for the places with a single run and no list to scan, where the
 * status has nothing to contrast against.
 */
const RunStatusBadge: FC<{ status: RunStatus; showDone?: boolean }> = ({
  status,
  showDone = false,
}) => {
  if (status === "done" && !showDone) return null;

  return (
    <Badge variant={VARIANTS[status]}>
      {status === "running" ? (
        <span aria-hidden className="size-1.5 animate-live-pulse rounded-full bg-current" />
      ) : null}
      {RUN_STATUS_LABELS[status]}
    </Badge>
  );
};

export default RunStatusBadge;
