import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import RunStatusBadge from "@/components/runs/run-status-badge";
import type { RunStatus } from "@/lib/types";

describe("RunStatusBadge", () => {
  it.each<[RunStatus, string]>([
    ["queued", "Queued"],
    ["running", "Running"],
    ["done", "Done"],
    ["failed", "Failed"],
  ])("labels %s", (status, label) => {
    render(<RunStatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});
