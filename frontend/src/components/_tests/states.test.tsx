import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EmptyState, ErrorState, LoadingRows } from "@/components/states";

describe("LoadingRows", () => {
  it("marks itself busy so it is not read as content", () => {
    const { container } = render(<LoadingRows rows={3} />);
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
  });
});

describe("EmptyState", () => {
  it("shows the title and the guidance", () => {
    render(
      <EmptyState title="No sequences registered">
        <p>Download a sequence first.</p>
      </EmptyState>,
    );
    expect(screen.getByText("No sequences registered")).toBeInTheDocument();
    expect(screen.getByText("Download a sequence first.")).toBeInTheDocument();
  });

  it("is not announced as an alert, because empty is not a failure", () => {
    render(<EmptyState title="No sequences registered" />);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("ErrorState", () => {
  it("announces itself as an alert so it cannot be mistaken for an empty result", () => {
    render(<ErrorState title="Could not load sequences" message="The server is unreachable." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load sequences");
  });

  it("offers a retry that calls back", async () => {
    const onRetry = vi.fn();
    render(<ErrorState title="Could not load" message="Try again." onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("omits the retry when there is nothing to retry", () => {
    render(<ErrorState title="Could not load" message="Gone." />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
