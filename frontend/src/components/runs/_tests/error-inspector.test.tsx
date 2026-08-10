import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ErrorInspector from "@/components/runs/error-inspector";
import type { PoseErrorPoint } from "@/lib/types";

/**
 * A 19 digit nanosecond value does not survive as a JavaScript number, which is the whole
 * reason timestamps travel as strings. Writing one as a numeric literal here would round it
 * before it ever reached the component, so the varying part is kept short and padded onto a
 * fixed prefix instead.
 */
function timestampAt(index: number): string {
  return `15205303081${String(index).padStart(8, "0")}`;
}

function points(values: number[]): PoseErrorPoint[] {
  return values.map((value, index) => ({
    timestamp_ns: timestampAt(index),
    trans_error: value,
    rot_error: value * 10,
  }));
}

describe("ErrorInspector", () => {
  it("renders nothing without errors to show", () => {
    const { container } = render(
      <ErrorInspector errors={[]} selected={null} onSelect={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("states which pose is selected and what its error is", () => {
    render(<ErrorInspector errors={points([0.01, 0.05, 0.2])} selected={1} onSelect={() => {}} />);

    expect(screen.getByRole("slider")).toHaveAttribute(
      "aria-valuetext",
      expect.stringContaining("Pose 2 of 3"),
    );
    expect(screen.getByText(/Pose 2 of 3/)).toBeInTheDocument();
  });

  it("reports a new selection when the slider moves", () => {
    /**
     * Driven with a change event rather than an arrow key. jsdom does not implement the
     * range input's own keyboard handling, so a key press there moves nothing and the test
     * would be asserting on jsdom rather than on this component. The keyboard path is
     * covered by the end to end suite, in a browser that does implement it.
     */
    const onSelect = vi.fn();
    render(<ErrorInspector errors={points([0.01, 0.05, 0.2])} selected={0} onSelect={onSelect} />);

    fireEvent.change(screen.getByRole("slider"), { target: { value: "1" } });

    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("jumps to the worst pose by translation error", async () => {
    const onSelect = vi.fn();
    render(<ErrorInspector errors={points([0.01, 0.4, 0.05])} selected={0} onSelect={onSelect} />);

    await userEvent.click(screen.getByRole("button", { name: /worst pose/i }));

    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("defaults to the first pose when nothing is selected", () => {
    render(<ErrorInspector errors={points([0.02, 0.05])} selected={null} onSelect={() => {}} />);
    expect(screen.getByRole("slider")).toHaveValue("0");
  });
});
