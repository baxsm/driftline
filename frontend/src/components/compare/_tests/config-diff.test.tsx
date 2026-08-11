import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ConfigDiff from "@/components/compare/config-diff";

describe("ConfigDiff", () => {
  it("says the configs are identical rather than drawing an empty table", () => {
    // an empty table with headers reads as the comparison failing to load
    render(<ConfigDiff rows={[]} labelA="Baseline" labelB="Tighter" />);

    expect(screen.getByText(/used identical settings/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows both values for a key that differs", () => {
    render(
      <ConfigDiff
        rows={[{ key: "max_features", a: 600, b: 900 }]}
        labelA="Baseline"
        labelB="Tighter"
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("Max features")).toBeInTheDocument();
    expect(screen.getByText("600")).toBeInTheDocument();
    expect(screen.getByText("900")).toBeInTheDocument();
  });

  it("reads a boolean as on and off rather than as true and false", () => {
    render(
      <ConfigDiff rows={[{ key: "enhance_contrast", a: true, b: false }]} labelA="A" labelB="B" />,
    );

    expect(screen.getByText("on")).toBeInTheDocument();
    expect(screen.getByText("off")).toBeInTheDocument();
  });

  it("shows an absent value as unset rather than as blank", () => {
    render(<ConfigDiff rows={[{ key: "max_frames", a: null, b: 500 }]} labelA="A" labelB="B" />);

    expect(screen.getByText("unset")).toBeInTheDocument();
  });
});
