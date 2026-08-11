"use client";

import { ChevronLeft, LogOut, Menu } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FC, type ReactNode, useState } from "react";
import { SidebarLinks } from "@/components/app-sidebar";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

interface AppTopbarProps {
  title: string;
  /**
   * Where this screen sits. A detail page reached from a list is otherwise a title with no
   * way back and nothing saying what it belongs to, which is how a reader ends up on a run
   * with no idea which sequence produced it.
   */
  parent?: { href: string; label: string };
  /** The primary action for the current screen, which is what this space is for. */
  action?: ReactNode;
}

const AppTopbar: FC<AppTopbarProps> = ({ title, parent, action }) => {
  const { signOut } = useAuth();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      // the provider drops the cache; this only has to leave the app
      await signOut();
      router.replace("/login");
      router.refresh();
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-border border-b px-4">
      <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open navigation">
            <Menu className="size-4" aria-hidden />
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-64 p-0">
          <SheetHeader className="h-14 justify-center border-border border-b px-4">
            <SheetTitle className="font-mono text-sm uppercase tracking-widest">
              driftline
            </SheetTitle>
          </SheetHeader>
          <div className="p-3">
            <SidebarLinks onNavigate={() => setMenuOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 items-center gap-1.5">
        {parent ? (
          <>
            <Link
              href={parent.href}
              className="flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-muted-foreground text-sm transition-colors duration-(--motion-quick) hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
            >
              <ChevronLeft className="size-3.5" aria-hidden />
              {parent.label}
            </Link>
            <span aria-hidden className="shrink-0 text-muted-foreground/50">
              /
            </span>
          </>
        ) : null}
        <h1 className="min-w-0 truncate font-medium text-sm">{title}</h1>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {action}
        <Button
          variant="ghost"
          size="icon"
          onClick={handleSignOut}
          disabled={signingOut}
          aria-label="Sign out"
          title="Sign out"
        >
          <LogOut className="size-4" aria-hidden />
        </Button>
      </div>
    </header>
  );
};

export default AppTopbar;
