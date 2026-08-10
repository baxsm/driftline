import type { DatasetSource, RunStatus } from "./types";

export const SOURCE_LABELS: Record<DatasetSource, string> = {
  tum_vi: "TUM VI",
  euroc: "EuRoC",
  custom: "Custom",
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

export function formatDate(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "unknown";
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
