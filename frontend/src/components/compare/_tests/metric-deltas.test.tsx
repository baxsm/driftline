import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MetricDeltas from "@/components/compare/metric-deltas";
import type { MetricDeltaRow } from "@/lib/types";

function row(over: Partial<MetricDeltaRow> = {}): MetricDeltaRow {
  return { key: "ate_rmse", a: 0.85, b: 0.53, delta: -0.32, comparable: true, ...over };
}

describe("MetricDeltas", () => {
  it("says which run improved rather than leaving a signed number to be read", () => {
    render(
      <MetricDeltas
        rows={[row()]}
        labelA="Baseline"
        labelB="Fused"
        alignmentA="sim3"
        alignmentB="sim3"
      />,
    );

    expect(screen.getByText("32.0 cm better")).toBeInTheDocument();
  });

  it("calls a positive delta worse", () => {
    render(
      <MetricDeltas
        rows={[row({ delta: 0.12 })]}
        labelA="A"
        labelB="B"
        alignmentA="sim3"
        alignmentB="sim3"
      />,
    );

    expect(screen.getByText("12.0 cm worse")).toBeInTheDocument();
  });

  it("withholds the delta and says why when the alignments differ", () => {
    // subtracting a Sim(3) ATE from an SE(3) one measures the alignment, not the estimator
    render(
      <MetricDeltas
        rows={[row({ delta: null, comparable: false })]}
        labelA="Mono"
        labelB="Fused"
        alignmentA="sim3"
        alignmentB="se3"
      />,
    );

    expect(screen.getByText("not comparable")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/aligned differently/);
    // both figures still render, so the reader sees them and why they were not subtracted
    expect(screen.getByText("85.0 cm")).toBeInTheDocument();
    expect(screen.getByText("53.0 cm")).toBeInTheDocument();
  });

  it("shows a metric missing on one side as not measured", () => {
    render(
      <MetricDeltas
        rows={[row({ key: "rpe_trans_rmse", a: null, b: 0.34, delta: null })]}
        labelA="A"
        labelB="B"
        alignmentA="sim3"
        alignmentB="sim3"
      />,
    );

    expect(screen.getByText("not measured")).toBeInTheDocument();
    expect(screen.getByText("34.0 cm")).toBeInTheDocument();
  });

  it("prints a rotation metric in degrees rather than metres", () => {
    render(
      <MetricDeltas
        rows={[row({ key: "rpe_rot_rmse", a: 5.16, b: 1.44, delta: -3.72 })]}
        labelA="A"
        labelB="B"
        alignmentA="se3"
        alignmentB="se3"
      />,
    );

    expect(screen.getByText("5.16°")).toBeInTheDocument();
    expect(screen.getByText("3.72° better")).toBeInTheDocument();
  });

  it("says nothing was scored rather than rendering an empty table", () => {
    // this is the failed-run case: the run exists, and there is no score to compare
    render(<MetricDeltas rows={[]} labelA="A" labelB="B" alignmentA={null} alignmentB={null} />);

    expect(screen.getByText(/never scored/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
