"use client";

import { Database, GitCompare, Route } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { FC } from "react";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/app/datasets", label: "Datasets", icon: Database },
  { href: "/app/runs", label: "Runs", icon: Route },
  { href: "/app/compare", label: "Compare", icon: GitCompare },
] as const;

interface AppSidebarProps {
  onNavigate?: () => void;
}

export const SidebarLinks: FC<AppSidebarProps> = ({ onNavigate }) => {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-0.5" aria-label="Main">
      {LINKS.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
              active
                ? "bg-muted font-medium text-foreground"
                : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
            )}
          >
            <Icon className="size-4 shrink-0" aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
};

const AppSidebar: FC = () => (
  <aside className="hidden w-56 shrink-0 flex-col border-border border-r bg-muted/10 md:flex">
    <div className="flex h-14 shrink-0 items-center border-border border-b px-4">
      <Link href="/app/datasets" className="font-mono text-sm uppercase tracking-widest">
        driftline
      </Link>
    </div>
    <div className="min-h-0 flex-1 overflow-y-auto p-3">
      <SidebarLinks />
    </div>
  </aside>
);

export default AppSidebar;
