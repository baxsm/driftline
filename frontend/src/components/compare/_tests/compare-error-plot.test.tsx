import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CompareErrorPlot from "@/components/compare/compare-error-plot";
import type { CompareErrorPoint } from "@/lib/types";

function series(count: number, scale: number, step = 1): CompareErrorPoint[] {
  return Array.from({ length: count }, (_, index) => ({
    t: index * step,
    trans_error: index * scale,
    rot_error: index * scale * 2,
  }));
}

/**
 * Recharts sizes itself from a ResizeObserver, which the jsdom stub never fires, so the lines
 * themselves are not in the DOM here. These cover the parts that are ours: the summary line,
 * the empty case, and which quantity is being read off each point. What is actually drawn is
 * checked in the browser by the Playwright suite.
 */
describe("CompareErrorPlot", () => {
  it("renders nothing when neither run scored a pose", () => {
    const { container } = render(
      <CompareErrorPlot a={[]} b={[]} labelA="A" labelB="B" kind="translation" />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("still draws when only one run has errors", () => {
    render(<CompareErrorPlot a={series(5, 0.1)} b={[]} labelA="A" labelB="B" kind="translation" />);

    expect(screen.getByText("Position error")).toBeInTheDocument();
  });

  it("reports the peak across both runs, not just the first", () => {
    render(
      <CompareErrorPlot
        a={series(3, 0.1)}
        b={series(3, 0.5)}
        labelA="A"
        labelB="B"
        kind="translation"
      />,
    );

    // b peaks at 1.0m, which is the taller of the two
    expect(screen.getByText(/peak 1\.000 m/)).toBeInTheDocument();
  });

  it("spans the longer run so a short one does not stretch to fill the width", () => {
    render(
      <CompareErrorPlot
        a={series(3, 0.1)}
        b={series(9, 0.1)}
        labelA="A"
        labelB="B"
        kind="translation"
      />,
    );

    expect(screen.getByText(/over 8\.0s/)).toBeInTheDocument();
  });

  it("reads rotation off the rotation field", () => {
    render(<CompareErrorPlot a={series(3, 1)} b={[]} labelA="A" labelB="B" kind="rotation" />);

    expect(screen.getByText("Rotation error")).toBeInTheDocument();
    // rot_error is twice trans_error in the fixture, so peak is 4 not 2
    expect(screen.getByText(/peak 4\.0/)).toBeInTheDocument();
  });
});
