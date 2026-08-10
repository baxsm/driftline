"use client";

import Link from "next/link";
import type { FC } from "react";
import AppTopbar from "@/components/app-topbar";

interface NotBuiltYetProps {
  title: string;
  heading: string;
  detail: string;
}

/**
 * An explicit "not built" screen rather than an empty state. An empty state here would read
 * as "you have no runs", which is a different and misleading claim while the estimator does
 * not exist.
 */
const NotBuiltYet: FC<NotBuiltYetProps> = ({ title, heading, detail }) => (
  <>
    <AppTopbar title={title} />
    <main className="min-h-0 flex-1 overflow-y-auto p-4 md:p-6">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 rounded-lg border border-border border-dashed px-6 py-10">
        <h2 className="font-medium text-sm">{heading}</h2>
        <p className="max-w-prose text-muted-foreground text-sm leading-relaxed">{detail}</p>
        <Link href="/app/datasets" className="text-foreground text-sm underline underline-offset-4">
          Go to datasets
        </Link>
      </div>
    </main>
  </>
);

export default NotBuiltYet;
