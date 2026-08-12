import type { AlignmentMode, DatasetSource, RunStatus } from "./types";

export const SOURCE_LABELS: Record<DatasetSource, string> = {
  tum_vi: "TUM VI",
  euroc: "EuRoC",
  custom: "Custom",
};

export const ALIGNMENT_LABELS: Record<AlignmentMode, string> = {
  se3: "SE(3)",
  sim3: "Sim(3)",
};

/**
 * What the alignment mode means for the numbers next to it, in one line.
 *
 * Shown rather than left to the reader because an ATE is only comparable against another
 * ATE aligned the same way, and Sim(3) means the scale was fitted rather than measured.
 */
export const ALIGNMENT_HINTS: Record<AlignmentMode, string> = {
  se3: "Rotation and offset fitted, scale left as the estimator produced it",
  sim3: "Rotation, offset and scale fitted, so distances follow ground truth",
};

export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  queued: "Queued",
  running: "Running",
  done: "Done",
  failed: "Failed",
};

/** Percent of frames processed, or null before the total is known. */
export function progressPercent(processed: number, total: number): number | null {
  if (!Number.isFinite(total) || total <= 0) return null;
  return Math.min(100, Math.round((processed / total) * 100));
}

/** A config hash is 64 hex characters, which is unreadable in a table. */
export function shortHash(hash: string): string {
  return hash.slice(0, 8);
}

export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "unknown";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds - minutes * 60);
  return rest === 0 ? `${minutes}m` : `${minutes}m ${rest}s`;
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

/** Sample rate in Hz, or null when the duration cannot support a rate. */
export function formatRate(count: number, seconds: number): string | null {
  if (!Number.isFinite(seconds) || seconds <= 0 || count <= 0) return null;
  return `${(count / seconds).toFixed(1)} Hz`;
}

/**
 * A distance error in metres, at a precision that suits its size.
 *
 * These span millimetres on a good run to metres on a broken one. A fixed number of decimals
 * either prints "0.00 m" for a 4mm error or six digits of noise for a 3m one, and both read
 * as the measurement being useless.
 */
export function formatMetres(value: number): string {
  if (!Number.isFinite(value)) return "unknown";
  const magnitude = Math.abs(value);
  if (magnitude < 0.01) return `${(value * 1000).toFixed(1)} mm`;
  if (magnitude < 1) return `${(value * 100).toFixed(1)} cm`;
  return `${value.toFixed(3)} m`;
}

export function formatDegrees(value: number): string {
  if (!Number.isFinite(value)) return "unknown";
  return `${value.toFixed(Math.abs(value) < 10 ? 2 : 1)}°`;
}

/**
 * The Sim(3) scale as a readable statement rather than a bare ratio.
 *
 * The factor is what the estimate had to be multiplied by to sit on truth. A factor below 1
 * therefore means the estimate had to shrink, so its distances were too large. Reading the
 * ratio the other way round is easy to do and inverts the meaning, so it is stated in words
 * once here rather than at each place it is shown.
 */
export function formatScale(scale: number): string {
  if (!Number.isFinite(scale) || scale <= 0) return "unknown";
  if (Math.abs(scale - 1) < 0.005) return "matches ground truth";
  return scale < 1 ? `${(1 / scale).toFixed(2)}x too large` : `${scale.toFixed(2)}x too small`;
}

/** A nanosecond tolerance as milliseconds, which is the unit it is reasoned about in. */
export function formatToleranceMs(nanoseconds: string): string {
  const parsed = Number(nanoseconds);
  if (!Number.isFinite(parsed)) return "unknown";
  return `${(parsed / 1e6).toFixed(0)} ms`;
}

export function formatDate(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "unknown";
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** Metric keys as the compare table names them, matching the run page's own labels. */
export const METRIC_LABELS: Record<string, string> = {
  ate_rmse: "ATE RMSE",
  ate_mean: "ATE mean",
  ate_median: "ATE median",
  ate_max: "ATE max",
  ate_rot_rmse: "Rotation offset",
  rpe_trans_rmse: "RPE translation",
  rpe_rot_rmse: "RPE rotation",
};

/** Which metrics are angles, so the compare table does not print degrees as metres. */
const ANGLE_METRICS = new Set(["ate_rot_rmse", "rpe_rot_rmse"]);

export function formatMetric(key: string, value: number | null): string {
  if (value === null) return "not measured";
  return ANGLE_METRICS.has(key) ? formatDegrees(value) : formatMetres(value);
}

/**
 * A delta with an explicit sign, because the sign is the whole message.
 *
 * Every metric in the table is one where lower is better, so a negative delta means run B
 * improved on run A. The sign is written out rather than left to the minus glyph alone, so a
 * positive delta cannot be misread as a plain figure.
 */
export function formatDelta(key: string, delta: number | null): string {
  if (delta === null) return "not comparable";
  if (delta === 0) return "no change";
  const magnitude = ANGLE_METRICS.has(key)
    ? formatDegrees(Math.abs(delta))
    : formatMetres(Math.abs(delta));
  return delta < 0 ? `${magnitude} better` : `${magnitude} worse`;
}

/** Config values render as text, and a null has to read as "unset" rather than as blank. */
export function formatConfigValue(value: unknown): string {
  if (value === null || value === undefined) return "unset";
  if (typeof value === "boolean") return value ? "on" : "off";
  return String(value);
}

/** Config keys as the run form names them, so the diff does not show raw snake_case. */
export const CONFIG_LABELS: Record<string, string> = {
  mode: "Mode",
  max_features: "Max features",
  corner_quality: "Corner quality",
  min_feature_distance_px: "Min feature distance",
  ransac_threshold_px: "RANSAC threshold",
  redetect_below: "Redetect below",
  min_track_length: "Min track length",
  max_frames: "Max frames",
  start_frame: "Start frame",
  enhance_contrast: "Enhance contrast",
  keyframe_parallax_px: "Keyframe parallax",
  max_frames_without_keyframe: "Max frames without keyframe",
};

export function configLabel(key: string): string {
  return CONFIG_LABELS[key] ?? key;
}

/**
 * The query window that limits ground truth to the span an estimate actually covers.
 *
 * Truth is recorded for the whole sequence, and a run can cover a slice of it: a 250 frame run
 * on room1 is about 12 seconds of a 141 second recording. Overlaying all of truth on that draws
 * a dense tangle the estimate disappears into, and implies the estimate spans a path it never
 * saw. The window is widened slightly at both ends so the truth line does not stop exactly on
 * the first and last estimated pose and read as if it had been clipped to fit.
 *
 * Timestamps stay strings throughout. A 19 digit nanosecond value does not survive a JavaScript
 * number, so it is never parsed on the way through.
 */
export function truthWindowQuery(
  poses: { timestamp_ns: string }[],
  paddingNs: bigint = BigInt(500_000_000),
): string {
  if (poses.length === 0) return "";

  const zero = BigInt(0);
  let low = BigInt(poses[0].timestamp_ns);
  let high = low;
  for (const pose of poses) {
    const value = BigInt(pose.timestamp_ns);
    if (value < low) low = value;
    if (value > high) high = value;
  }

  const from = low - paddingNs;
  return `&from=${from < zero ? zero : from}&to=${high + paddingNs}`;
}
