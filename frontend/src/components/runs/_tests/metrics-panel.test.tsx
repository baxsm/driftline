import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MetricsPanel from "@/components/runs/metrics-panel";
import type { MetricsResponse, RunMetrics } from "@/lib/types";

function metrics(overrides: Partial<RunMetrics> = {}): RunMetrics {
  return {
    ate_rmse: 0.042,
    ate_mean: 0.038,
    ate_median: 0.036,
    ate_max: 0.091,
    ate_rot_rmse: 2.4,
    ate_rot_std: 0.3,
    rpe_trans_rmse: 0.012,
    rpe_rot_rmse: 0.8,
    rpe_delta_frames: 20,
    scale_error: 0.4,
    alignment: "sim3",
    aligned_pose_count: 300,
    candidate_pose_count: 300,
    association_tolerance_ns: "20000000",
    computed_at: "2026-08-10T12:00:00Z",
    ...overrides,
  };
}

function response(overrides: Partial<MetricsResponse> = {}): MetricsResponse {
  return { metrics: metrics(), has_ground_truth: true, status: "done", ...overrides };
}

describe("MetricsPanel", () => {
  it("shows the alignment mode next to the numbers", () => {
    render(<MetricsPanel metrics={response()} status="done" />);
    expect(screen.getByText("Sim(3) aligned")).toBeInTheDocument();
  });

  it("says there is no ground truth rather than showing zeros", () => {
    render(
      <MetricsPanel metrics={response({ metrics: null, has_ground_truth: false })} status="done" />,
    );
    expect(screen.getByText(/no ground truth/i)).toBeInTheDocument();
    expect(screen.queryByText("ATE RMSE")).not.toBeInTheDocument();
  });

  it("says a scorable run was not scored rather than showing zeros", () => {
    render(<MetricsPanel metrics={response({ metrics: null })} status="done" />);
    expect(screen.getByText(/was not scored/i)).toBeInTheDocument();
    expect(screen.queryByText("ATE RMSE")).not.toBeInTheDocument();
  });

  it("warns when only part of the run was matched", () => {
    render(
      <MetricsPanel
        metrics={response({ metrics: metrics({ aligned_pose_count: 30 }) })}
        status="done"
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("10%");
  });

  it("does not warn when nearly every pose matched", () => {
    render(<MetricsPanel metrics={response()} status="done" />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("reports scale as a readable factor for a mono run", () => {
    // the estimate had to be multiplied by 0.4 to sit on truth, so it was too large
    render(<MetricsPanel metrics={response()} status="done" />);
    expect(screen.getByText("2.50x too large")).toBeInTheDocument();
  });

  it("says scale was not fitted under se3", () => {
    render(
      <MetricsPanel
        metrics={response({ metrics: metrics({ alignment: "se3", scale_error: null }) })}
        status="done"
      />,
    );
    expect(screen.getByText("not fitted")).toBeInTheDocument();
    expect(screen.getByText("SE(3) aligned")).toBeInTheDocument();
  });

  it("says rpe was not measured on a run too short for a segment", () => {
    render(
      <MetricsPanel
        metrics={response({
          metrics: metrics({ rpe_trans_rmse: null, rpe_rot_rmse: null }),
        })}
        status="done"
      />,
    );
    expect(screen.getAllByText("not measured")).toHaveLength(2);
  });

  it("warns that a sim3 figure is not comparable to an se3 one", () => {
    render(<MetricsPanel metrics={response()} status="done" />);
    expect(screen.getByText(/cannot be compared against an SE\(3\)/i)).toBeInTheDocument();
  });

  it("says scores arrive later while the run is still going", () => {
    render(<MetricsPanel metrics={null} status="running" />);
    expect(screen.getByText(/computed when the run finishes/i)).toBeInTheDocument();
  });

  it("reports a failure to load rather than claiming there is no truth", () => {
    render(<MetricsPanel metrics={null} status="done" />);
    expect(screen.getByText(/could not load/i)).toBeInTheDocument();
  });
});
