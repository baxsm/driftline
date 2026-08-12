import DatasetDetailScreen from "@/components/datasets/dataset-detail-screen";

export const metadata = { title: "Sequence - driftline" };

export default async function DatasetPage({ params }: PageProps<"/app/datasets/[id]">) {
  const { id } = await params;
  return <DatasetDetailScreen datasetId={id} />;
}
