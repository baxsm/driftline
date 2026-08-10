import RunDetailScreen from "@/components/runs/run-detail-screen";

export const metadata = { title: "Run - driftline" };

export default async function RunPage({ params }: PageProps<"/app/runs/[id]">) {
  const { id } = await params;
  return <RunDetailScreen runId={id} />;
}
