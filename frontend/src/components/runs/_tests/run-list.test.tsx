import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import RunList from "@/components/runs/run-list";
import type { RunSummary } from "@/lib/types";

const DONE: RunSummary = {
  id: "11111111-1111-1111-1111-111111111111",
  dataset_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  dataset_name: "dataset-room1_512_16",
  label: "Baseline mono",
  config_hash: "d2ccd2e94f1b8c7a5e6d0f3b2a1c9e8d7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c",
  status: "done",
  failure_reason: null,
  processed_frames: 2821,
  total_frames: 2821,
  created_at: "2026-08-10T10:00:00+00:00",
  finished_at: "2026-08-10T10:04:00+00:00",
  ate_rmse: 0.853,
  alignment: "sim3",
};

const FAILED: RunSummary = {
  ...DONE,
  id: "22222222-2222-2222-2222-222222222222",
  label: null,
  status: "failed",
  failure_reason: "only 3 tracked features, need 8",
  processed_frames: 412,
  ate_rmse: null,
  alignment: null,
};

const RUNNING: RunSummary = {
  ...DONE,
  id: "33333333-3333-3333-3333-333333333333",
  label: "Tighter RANSAC",
  status: "running",
  processed_frames: 1410,
  ate_rmse: null,
  alignment: null,
};

/** A run on another sequence, which cannot be compared against one of these. */
const OTHER_SEQUENCE: RunSummary = {
  ...DONE,
  id: "44444444-4444-4444-4444-444444444444",
  dataset_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  dataset_name: "dataset-corridor1",
  label: "Corridor baseline",
};

function renderList(runs: RunSummary[], pendingId: string | null = null, showDataset = true) {
  const onDelete = vi.fn();
  render(
    <RunList runs={runs} onDelete={onDelete} pendingId={pendingId} showDataset={showDataset} />,
  );
  return { onDelete };
}

describe("RunList", () => {
  it("shows how far a run got against its total", () => {
    renderList([DONE]);
    expect(screen.getByText(/2,821 of 2,821 frames/)).toBeInTheDocument();
  });

  it("shows a percentage only while a run is still going", () => {
    renderList([RUNNING]);
    expect(screen.getByText(/50%/)).toBeInTheDocument();
  });

  it("does not show a percentage on a finished run", () => {
    renderList([DONE]);
    expect(screen.queryByText(/100%/)).toBeNull();
  });

  it("surfaces why a run failed", () => {
    // a failed run that only says "failed" sends the user to the logs for no reason
    renderList([FAILED]);
    expect(screen.getByText("only 3 tracked features, need 8")).toBeInTheDocument();
  });

  it("shows no failure text on a run that succeeded", () => {
    renderList([DONE]);
    expect(screen.queryByText(/need 8/)).toBeNull();
  });

  it("falls back to a short id when a run has no label", () => {
    renderList([FAILED]);
    expect(screen.getByRole("link", { name: "Run 22222222" })).toBeInTheDocument();
  });

  it("shortens the config hash", () => {
    renderList([DONE]);
    expect(screen.getByText("d2ccd2e9")).toBeInTheDocument();
    expect(screen.queryByText(DONE.config_hash)).toBeNull();
  });

  it("links each row to its run", () => {
    renderList([DONE]);
    expect(screen.getByRole("link", { name: "Baseline mono" })).toHaveAttribute(
      "href",
      `/app/runs/${DONE.id}`,
    );
  });

  it("hides the dataset name where every row shares it", () => {
    renderList([DONE], null, false);
    expect(screen.queryByText("dataset-room1_512_16")).toBeNull();
  });

  it("shows the dataset name on the all runs list", () => {
    renderList([DONE]);
    expect(screen.getByText("dataset-room1_512_16")).toBeInTheDocument();
  });

  it("hands the row back when delete is pressed", async () => {
    const { onDelete } = renderList([DONE]);
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onDelete).toHaveBeenCalledWith(DONE);
  });

  it("disables the row being deleted", () => {
    renderList([DONE], DONE.id);
    expect(screen.getByRole("button", { name: "Deleting" })).toBeDisabled();
  });

  it("shows the ATE with the alignment it was measured under", () => {
    // a bare ATE invites ranking two runs that were never measuring the same thing
    renderList([DONE]);
    expect(screen.getByText("85.3 cm")).toBeInTheDocument();
    expect(screen.getByText("ATE, Sim(3)")).toBeInTheDocument();
  });

  it("says a finished run was not scored rather than showing a zero", () => {
    renderList([FAILED]);
    expect(screen.getByText("not scored")).toBeInTheDocument();
    expect(screen.queryByText("0.0 mm")).toBeNull();
  });

  it("says a run still going has no score yet", () => {
    renderList([RUNNING]);
    expect(screen.getByText("no score yet")).toBeInTheDocument();
  });

  it("offers no selection when comparing is not on", () => {
    renderList([DONE]);
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("hands the id back when a row is picked", async () => {
    const onToggle = vi.fn();
    render(
      <RunList
        runs={[DONE]}
        onDelete={vi.fn()}
        pendingId={null}
        selected={[]}
        onToggle={onToggle}
      />,
    );

    await userEvent.click(screen.getByRole("checkbox"));

    expect(onToggle).toHaveBeenCalledWith(DONE.id);
  });

  it("blocks a run on another sequence, because there is no common ground truth", () => {
    render(
      <RunList
        runs={[DONE, OTHER_SEQUENCE]}
        onDelete={vi.fn()}
        pendingId={null}
        selected={[DONE.id]}
        onToggle={vi.fn()}
        disabledReason={(run) =>
          run.dataset_id === DONE.dataset_id ? null : "On a different sequence."
        }
      />,
    );

    const [first, second] = screen.getAllByRole("checkbox");
    expect(first).toBeChecked();
    expect(second).toBeDisabled();
  });
});
