import NotBuiltYet from "@/components/not-built-yet";

export const metadata = { title: "Compare - driftline" };

export default function ComparePage() {
  return (
    <NotBuiltYet
      title="Compare"
      heading="Comparing runs needs runs to compare"
      detail="This screen puts two runs side by side with their config diff and metric deltas. It arrives after the estimator and the scoring that measures it."
    />
  );
}
