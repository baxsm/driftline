import type { FC } from "react";
import { Badge } from "@/components/ui/badge";
import { RUN_STATUS_LABELS } from "@/lib/format";
import type { RunStatus } from "@/lib/types";

/**
 * Failed is the only status that gets the destructive treatment. Done stays neutral because a
 * finished run is not a success claim on its own: this phase has no scoring, so "done" means
 * the estimator reached the last frame, not that the trajectory is any good.
 */
const VARIANTS: Record<RunStatus, "default" | "secondary" | "destructive" | "outline"> = {
  queued: "outline",
  running: "secondary",
  done: "outline",
  failed: "destructive",
};

const RunStatusBadge: FC<{ status: RunStatus }> = ({ status }) => (
  <Badge variant={VARIANTS[status]}>{RUN_STATUS_LABELS[status]}</Badge>
);

export default RunStatusBadge;
