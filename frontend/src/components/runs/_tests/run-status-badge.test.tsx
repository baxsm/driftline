import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import RunStatusBadge from "@/components/runs/run-status-badge";
import type { RunStatus } from "@/lib/types";

describe("RunStatusBadge", () => {
  it.each<[RunStatus, string]>([
    ["queued", "Queued"],
    ["running", "Running"],
    ["failed", "Failed"],
  ])("labels %s", (status, label) => {
    render(<RunStatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  // in a list where most rows finished, a badge on each one buries the two that did not
  it("renders nothing for a finished run", () => {
    const { container } = render(<RunStatusBadge status="done" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("labels a finished run where it stands alone", () => {
    render(<RunStatusBadge status="done" showDone />);
    expect(screen.getByText("Done")).toBeInTheDocument();
  });
});
