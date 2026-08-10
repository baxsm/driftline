import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import DatasetList from "@/components/datasets/dataset-list";
import type { DatasetSummary } from "@/lib/types";

const WITH_TRUTH: DatasetSummary = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "dataset-room1_512_16",
  source: "tum_vi",
  has_ground_truth: true,
  frame_count: 2821,
  imu_sample_count: 30943,
  duration_seconds: 141.05,
  camera_model: "pinhole-equi",
  created_at: "2026-08-10T10:00:00+00:00",
};

const WITHOUT_TRUTH: DatasetSummary = {
  ...WITH_TRUTH,
  id: "22222222-2222-2222-2222-222222222222",
  name: "handheld-office",
  source: "custom",
  has_ground_truth: false,
  camera_model: null,
};

function renderList(datasets: DatasetSummary[], pendingId: string | null = null) {
  const onUnregister = vi.fn();
  render(<DatasetList datasets={datasets} onUnregister={onUnregister} pendingId={pendingId} />);
  return { onUnregister };
}

describe("DatasetList", () => {
  it("shows the counts and duration in readable units", () => {
    renderList([WITH_TRUTH]);
    expect(screen.getByText("2,821 frames")).toBeInTheDocument();
    expect(screen.getByText("30,943 IMU samples")).toBeInTheDocument();
    expect(screen.getByText("2m 21s")).toBeInTheDocument();
  });

  it("labels the source", () => {
    renderList([WITH_TRUTH]);
    expect(screen.getByText("TUM VI")).toBeInTheDocument();
  });

  it("says plainly when a sequence has no ground truth", () => {
    // a sequence without truth can be run but never scored, so this cannot be silent
    renderList([WITHOUT_TRUTH]);
    expect(screen.getByText("No ground truth")).toBeInTheDocument();
  });

  it("marks a sequence that has ground truth", () => {
    renderList([WITH_TRUTH]);
    expect(screen.getByText("Ground truth")).toBeInTheDocument();
  });

  it("links each row to its sequence", () => {
    renderList([WITH_TRUTH]);
    expect(screen.getByRole("link", { name: WITH_TRUTH.name })).toHaveAttribute(
      "href",
      `/app/datasets/${WITH_TRUTH.id}`,
    );
  });

  it("hands the row back when unregister is pressed", async () => {
    const { onUnregister } = renderList([WITH_TRUTH]);
    await userEvent.click(screen.getByRole("button", { name: "Unregister" }));
    expect(onUnregister).toHaveBeenCalledWith(WITH_TRUTH);
  });

  it("disables the row being removed", () => {
    renderList([WITH_TRUTH], WITH_TRUTH.id);
    expect(screen.getByRole("button", { name: "Removing" })).toBeDisabled();
  });

  it("omits the camera model when the reader did not find one", () => {
    renderList([WITHOUT_TRUTH]);
    expect(screen.queryByText("pinhole-equi")).toBeNull();
  });
});
