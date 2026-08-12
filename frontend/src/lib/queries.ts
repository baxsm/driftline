"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  Dataset,
  DatasetSummary,
  GroundTruthResponse,
  MetricsResponse,
  PoseErrorsResponse,
  Run,
  RunSort,
  RunStatus,
  RunSummary,
  TrajectoryResponse,
} from "@/lib/types";

/**
 * Every cache key in one place.
 *
 * Keys built at the call site drift: one screen invalidates `["runs"]` while another stored
 * `["run-list"]`, and the list quietly stops refreshing after a delete. Everything reads from
 * here so a prefix always matches what was written under it.
 */
export const keys = {
  datasets: () => ["datasets"] as const,
  dataset: (id: string) => ["dataset", id] as const,
  groundTruth: (id: string, stride: number, window?: string) =>
    ["dataset", id, "ground-truth", stride, window ?? "full"] as const,
  runs: (filters?: { datasetId?: string; sort?: RunSort; status?: RunStatus | "all" }) =>
    ["runs", filters ?? {}] as const,
  run: (id: string) => ["run", id] as const,
  metrics: (id: string) => ["run", id, "metrics"] as const,
  trajectory: (id: string, aligned: boolean) => ["run", id, "trajectory", aligned] as const,
  errors: (id: string) => ["run", id, "errors"] as const,
};

/** A run that is still executing has to be polled; a finished one never changes again. */
const LIVE_MS = 2000;
export function isInFlight(status: RunStatus | undefined): boolean {
  return status === "queued" || status === "running";
}

export function useDatasets() {
  return useQuery({
    queryKey: keys.datasets(),
    queryFn: () => api.get<{ datasets: DatasetSummary[] }>("/api/datasets"),
    select: (data) => data.datasets,
  });
}

export function useDataset(id: string) {
  return useQuery({
    queryKey: keys.dataset(id),
    queryFn: () => api.get<Dataset>(`/api/datasets/${id}`),
  });
}

export function useGroundTruth(
  datasetId: string | undefined,
  stride: number,
  window?: { from: string; to: string },
) {
  const query = window ? `&from=${window.from}&to=${window.to}` : "";
  return useQuery({
    queryKey: keys.groundTruth(datasetId ?? "", stride, window && `${window.from}-${window.to}`),
    queryFn: () =>
      api.get<GroundTruthResponse>(
        `/api/datasets/${datasetId}/ground-truth?stride=${stride}${query}`,
      ),
    enabled: Boolean(datasetId),
  });
}

export function useRuns(filters: {
  datasetId?: string;
  sort?: RunSort;
  status?: RunStatus | "all";
}) {
  const { datasetId, sort, status } = filters;
  const params = new URLSearchParams();
  if (datasetId) params.set("dataset_id", datasetId);
  if (sort) params.set("sort", sort);
  if (status && status !== "all") params.set("status", status);
  const search = params.toString();

  return useQuery({
    queryKey: keys.runs(filters),
    queryFn: () =>
      api.get<{ runs: RunSummary[]; total: number }>(`/api/runs${search ? `?${search}` : ""}`),
    select: (data) => data.runs,
    // a list holding anything unfinished refreshes itself; one that does not, does not
    refetchInterval: (query) =>
      query.state.data?.runs.some((run) => isInFlight(run.status)) ? LIVE_MS : false,
  });
}

export function useRun(id: string) {
  return useQuery({
    queryKey: keys.run(id),
    queryFn: () => api.get<Run>(`/api/runs/${id}`),
    refetchInterval: (query) => (isInFlight(query.state.data?.status) ? LIVE_MS : false),
  });
}

/**
 * Scores for a run.
 *
 * Only asked for once the run has stopped. A queued run has nothing to score, and asking
 * anyway caches a "no metrics" answer under the key the finished run will read.
 */
export function useMetrics(id: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.metrics(id),
    queryFn: () => api.get<MetricsResponse>(`/api/runs/${id}/metrics`),
    enabled,
  });
}

export function useTrajectory(id: string, aligned: boolean, enabled: boolean) {
  return useQuery({
    queryKey: keys.trajectory(id, aligned),
    queryFn: () =>
      api.get<TrajectoryResponse>(`/api/runs/${id}/trajectory${aligned ? "?aligned=true" : ""}`),
    enabled,
  });
}

export function usePoseErrors(id: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.errors(id),
    queryFn: () => api.get<PoseErrorsResponse>(`/api/runs/${id}/errors`),
    enabled,
  });
}

/** Drops every cached run and list, for after a delete or a newly queued run. */
export function useInvalidateRuns() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: ["runs"] });
    void client.invalidateQueries({ queryKey: ["run"] });
  };
}
