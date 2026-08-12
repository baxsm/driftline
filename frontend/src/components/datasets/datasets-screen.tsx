"use client";

import { useQueryClient } from "@tanstack/react-query";
import { type FC, useState } from "react";
import { toast } from "sonner";
import AppTopbar from "@/components/app-topbar";
import DatasetList from "@/components/datasets/dataset-list";
import RegisterDatasetDialog from "@/components/datasets/register-dataset-dialog";
import { EmptyState, ErrorState, LoadingRows } from "@/components/states";
import { ApiError, api } from "@/lib/api";
import { keys, useDatasets } from "@/lib/queries";
import type { Dataset, DatasetSummary } from "@/lib/types";

const TUM_VI_URL =
  "https://cdn3.vision.in.tum.de/tumvi/exported/euroc/512_16/dataset-room1_512_16.tar";

const DatasetsScreen: FC = () => {
  const [pendingId, setPendingId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const datasetsQuery = useDatasets();
  const datasets = datasetsQuery.data ?? null;

  const refreshDatasets = () => queryClient.invalidateQueries({ queryKey: keys.datasets() });

  async function handleRegister(path: string, name: string) {
    const created = await api.post<Dataset>("/api/datasets/register", {
      path,
      ...(name ? { name } : {}),
    });
    await refreshDatasets();
    toast.success(`Registered ${created.name}`, {
      description: created.has_ground_truth
        ? `${created.frame_count.toLocaleString("en-US")} frames with ground truth`
        : `${created.frame_count.toLocaleString("en-US")} frames, no ground truth`,
    });
  }

  async function handleUnregister(dataset: DatasetSummary) {
    setPendingId(dataset.id);
    try {
      await api.delete(`/api/datasets/${dataset.id}`);
      await refreshDatasets();
      // the runs scored against it went with it, so any cached list holding them is stale
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      toast.success(`Unregistered ${dataset.name}`, {
        description: "The files on disk were not touched.",
      });
    } catch (caught) {
      toast.error(
        caught instanceof ApiError ? caught.message : "Could not unregister that sequence.",
      );
    } finally {
      setPendingId(null);
    }
  }

  return (
    <>
      <AppTopbar title="Datasets" action={<RegisterDatasetDialog onRegister={handleRegister} />} />

      <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
          {datasetsQuery.isError ? (
            <ErrorState
              title="Could not load sequences"
              message={
                datasetsQuery.error instanceof ApiError
                  ? datasetsQuery.error.message
                  : "Could not load your sequences."
              }
              onRetry={() => void datasetsQuery.refetch()}
            />
          ) : datasetsQuery.isPending || datasets === null ? (
            <LoadingRows />
          ) : datasets.length === 0 ? (
            <EmptyState title="No sequences registered">
              <p>
                driftline reads sequences in the ASL folder layout, the one TUM VI and EuRoC both
                ship. Download a sequence, unpack it, then register the folder that holds{" "}
                <span className="font-mono">mav0</span>.
              </p>
              <p className="mt-3 break-all font-mono text-foreground text-xs">{TUM_VI_URL}</p>
              <p className="mt-1 text-xs">
                1.7 GB. The room sequences carry ground truth for the whole trajectory.
              </p>
            </EmptyState>
          ) : (
            <DatasetList
              datasets={datasets}
              onUnregister={handleUnregister}
              pendingId={pendingId}
            />
          )}
        </div>
      </main>
    </>
  );
};

export default DatasetsScreen;
