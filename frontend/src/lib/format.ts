import type { DatasetSource } from "./types";

export const SOURCE_LABELS: Record<DatasetSource, string> = {
  tum_vi: "TUM VI",
  euroc: "EuRoC",
  custom: "Custom",
};

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
