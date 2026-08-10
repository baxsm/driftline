import NotBuiltYet from "@/components/not-built-yet";

export const metadata = { title: "Runs - driftline" };

export default function RunsPage() {
  return (
    <NotBuiltYet
      title="Runs"
      heading="The estimator is not built yet"
      detail="Runs appear here once the visual odometry front end lands. Nothing queues a run today, so this page has no data to show rather than no runs to show."
    />
  );
}
