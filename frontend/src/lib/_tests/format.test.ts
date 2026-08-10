import { describe, expect, it } from "vitest";
import {
  formatCount,
  formatDate,
  formatDegrees,
  formatDuration,
  formatMetres,
  formatRate,
  formatScale,
  formatToleranceMs,
  progressPercent,
  SOURCE_LABELS,
  shortHash,
} from "@/lib/format";

describe("formatScale", () => {
  /**
   * The scale is the factor the estimate was multiplied by to sit on truth, so a factor
   * below 1 means it had to shrink and its distances were too large. Stating it the wrong
   * way round is invisible in the UI and inverts the meaning, so the direction is pinned
   * here. Verified against the scorer: an estimate ten times too large returns 0.1.
   */
  it("calls an estimate that had to shrink too large", () => {
    expect(formatScale(0.1)).toBe("10.00x too large");
    expect(formatScale(0.4)).toBe("2.50x too large");
  });

  it("calls an estimate that had to grow too small", () => {
    expect(formatScale(10)).toBe("10.00x too small");
  });

  it("says a scale of one matches", () => {
    expect(formatScale(1)).toBe("matches ground truth");
    expect(formatScale(1.001)).toBe("matches ground truth");
  });

  it("refuses a scale that cannot be a ratio", () => {
    expect(formatScale(0)).toBe("unknown");
    expect(formatScale(Number.NaN)).toBe("unknown");
  });
});

describe("formatMetres", () => {
  it("uses a unit that suits the size of the error", () => {
    expect(formatMetres(0.004)).toBe("4.0 mm");
    expect(formatMetres(0.042)).toBe("4.2 cm");
    expect(formatMetres(3.5)).toBe("3.500 m");
  });

  it("reports a non finite value as unknown rather than NaN", () => {
    expect(formatMetres(Number.NaN)).toBe("unknown");
  });
});

describe("formatDegrees", () => {
  it("keeps more precision on a small angle", () => {
    expect(formatDegrees(2.456)).toBe("2.46°");
    expect(formatDegrees(24.56)).toBe("24.6°");
  });
});

describe("formatToleranceMs", () => {
  it("reads a nanosecond tolerance as milliseconds", () => {
    expect(formatToleranceMs("20000000")).toBe("20 ms");
  });
});

describe("progressPercent", () => {
  it("reports how far through a run is", () => {
    expect(progressPercent(1410, 2821)).toBe(50);
  });

  it("returns null before the total is known", () => {
    // 0 of 0 is not 0 percent, it is "no idea yet", and rendering 0% would look like a stall
    expect(progressPercent(0, 0)).toBeNull();
  });

  it("never exceeds 100", () => {
    expect(progressPercent(3000, 2821)).toBe(100);
  });
});

describe("shortHash", () => {
  it("keeps the leading eight characters", () => {
    expect(shortHash("d2ccd2e94f1b8c7a5e6d0f3b")).toBe("d2ccd2e9");
  });
});

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
