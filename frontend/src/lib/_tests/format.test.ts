import { describe, expect, it } from "vitest";
import { formatCount, formatDate, formatDuration, formatRate, SOURCE_LABELS } from "@/lib/format";

describe("formatDuration", () => {
  it("shows seconds below a minute", () => {
    expect(formatDuration(41.5)).toBe("41.5s");
  });

  it("shows minutes and seconds above a minute", () => {
    expect(formatDuration(141.05)).toBe("2m 21s");
  });

  it("drops the seconds when they round to zero", () => {
    expect(formatDuration(120)).toBe("2m");
  });

  it("says unknown rather than guessing on a bad value", () => {
    expect(formatDuration(Number.NaN)).toBe("unknown");
    expect(formatDuration(-1)).toBe("unknown");
  });
});

describe("formatRate", () => {
  it("computes hz from a count and a duration", () => {
    expect(formatRate(2821, 141.004)).toBe("20.0 Hz");
  });

  it("returns null instead of dividing by zero", () => {
    expect(formatRate(100, 0)).toBeNull();
  });

  it("returns null for an empty stream", () => {
    expect(formatRate(0, 141)).toBeNull();
  });
});

describe("formatCount", () => {
  it("groups thousands", () => {
    expect(formatCount(16541)).toBe("16,541");
  });
});

describe("formatDate", () => {
  it("uses the local day, not the utc day", () => {
    // a utc conversion would roll this to the next or previous day depending on the offset
    const local = new Date(2026, 7, 10, 23, 30);
    expect(formatDate(local.toISOString())).toBe("2026-08-10");
  });

  it("says unknown for an unparseable value", () => {
    expect(formatDate("not a date")).toBe("unknown");
  });
});

describe("SOURCE_LABELS", () => {
  it("names every source the reader can report", () => {
    expect(SOURCE_LABELS.tum_vi).toBe("TUM VI");
    expect(SOURCE_LABELS.euroc).toBe("EuRoC");
    expect(SOURCE_LABELS.custom).toBe("Custom");
  });
});
