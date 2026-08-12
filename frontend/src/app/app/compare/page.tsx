import CompareScreen from "@/components/compare/compare-screen";

export const metadata = { title: "Compare - driftline" };

/** A single id is not a comparison, so anything other than both present renders the picker. */
function single(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}

export default async function ComparePage({ searchParams }: PageProps<"/app/compare">) {
  const { run_a, run_b } = await searchParams;
  return <CompareScreen runA={single(run_a)} runB={single(run_b)} />;
}
