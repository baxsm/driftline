import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import RunConfigForm from "@/components/runs/run-config-form";

async function openForm(onQueue = vi.fn().mockResolvedValue(undefined)) {
  render(<RunConfigForm frameCount={2821} onQueue={onQueue} />);
  await userEvent.click(screen.getByRole("button", { name: "New run" }));
  return { onQueue };
}

describe("RunConfigForm", () => {
  it("opens with the server's defaults", async () => {
    await openForm();
    expect(screen.getByLabelText("Max features")).toHaveValue(600);
    expect(screen.getByLabelText("RANSAC threshold")).toHaveValue(1);
  });

  it("shows the accepted range for each field", async () => {
    await openForm();
    expect(screen.getByText("50 to 2000")).toBeInTheDocument();
    expect(screen.getByText("pixels, 0 to 10")).toBeInTheDocument();
  });

  it("says how many frames a run covers by default", async () => {
    await openForm();
    expect(screen.getByPlaceholderText("All 2,821 frames")).toBeInTheDocument();
  });

  it("queues with the defaults when nothing is changed", async () => {
    const { onQueue } = await openForm();
    await userEvent.click(screen.getByRole("button", { name: "Queue run" }));
    expect(onQueue).toHaveBeenCalledWith(
      expect.objectContaining({ mode: "mono", max_features: 600, max_frames: null }),
      "",
    );
  });

  it("rejects a value below the server's minimum without asking the server", async () => {
    const { onQueue } = await openForm();
    const field = screen.getByLabelText("Max features");
    await userEvent.clear(field);
    await userEvent.type(field, "5");
    await userEvent.click(screen.getByRole("button", { name: "Queue run" }));

    expect(screen.getByRole("alert")).toHaveTextContent("between 50 and 2000");
    expect(onQueue).not.toHaveBeenCalled();
  });

  it("marks the offending field rather than only the message", async () => {
    await openForm();
    const field = screen.getByLabelText("Max features");
    await userEvent.clear(field);
    await userEvent.type(field, "5000");
    await userEvent.click(screen.getByRole("button", { name: "Queue run" }));
    expect(field).toHaveAttribute("aria-invalid", "true");
  });

  it("rejects a frame limit below two", async () => {
    const { onQueue } = await openForm();
    await userEvent.type(screen.getByLabelText("Frame limit"), "1");
    await userEvent.click(screen.getByRole("button", { name: "Queue run" }));
    expect(screen.getByRole("alert")).toHaveTextContent("at least 2");
    expect(onQueue).not.toHaveBeenCalled();
  });

  it("passes a frame limit through when one is given", async () => {
    const { onQueue } = await openForm();
    await userEvent.type(screen.getByLabelText("Frame limit"), "200");
    await userEvent.click(screen.getByRole("button", { name: "Queue run" }));
    expect(onQueue).toHaveBeenCalledWith(expect.objectContaining({ max_frames: 200 }), "");
  });

  it("passes the label through", async () => {
    const { onQueue } = await openForm();
    await userEvent.type(screen.getByLabelText("Label"), "Tighter RANSAC");
    await userEvent.click(screen.getByRole("button", { name: "Queue run" }));
    expect(onQueue).toHaveBeenCalledWith(expect.anything(), "Tighter RANSAC");
  });

  it("offers no control for anything this phase does not estimate", async () => {
    // a knob that changes nothing is worse than no knob, so IMU and window settings arrive
    // with the phases that use them
    await openForm();
    expect(screen.queryByLabelText(/imu/i)).toBeNull();
    expect(screen.queryByLabelText(/sliding window/i)).toBeNull();
    expect(screen.queryByLabelText(/gravity/i)).toBeNull();
  });

  it("passes the keyframe and range settings through", async () => {
    const { onQueue } = await openForm();
    await userEvent.click(screen.getByRole("button", { name: "Queue run" }));
    expect(onQueue).toHaveBeenCalledWith(
      expect.objectContaining({
        keyframe_parallax_px: 8,
        enhance_contrast: true,
        start_frame: 0,
      }),
      "",
    );
  });

  it("rejects a start frame past the end of the sequence", async () => {
    const { onQueue } = await openForm();
    const field = screen.getByLabelText("Start frame");
    await userEvent.clear(field);
    await userEvent.type(field, "99999");
    await userEvent.click(screen.getByRole("button", { name: "Queue run" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Start frame must be between");
    expect(onQueue).not.toHaveBeenCalled();
  });

  it("turns contrast equalisation off when unchecked", async () => {
    const { onQueue } = await openForm();
    await userEvent.click(screen.getByLabelText(/equalise contrast/i));
    await userEvent.click(screen.getByRole("button", { name: "Queue run" }));
    expect(onQueue).toHaveBeenCalledWith(expect.objectContaining({ enhance_contrast: false }), "");
  });

  it("keeps the button disabled while a queue is in flight", async () => {
    let release = () => {};
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    await openForm(vi.fn().mockReturnValue(pending));

    await userEvent.click(screen.getByRole("button", { name: "Queue run" }));
    expect(screen.getByRole("button", { name: "Queueing" })).toBeDisabled();
    release();
  });
});
