"use client";

import { LogOut, Menu } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FC, type ReactNode, useState } from "react";
import { SidebarLinks } from "@/components/app-sidebar";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

interface AppTopbarProps {
  title: string;
  /** The primary action for the current screen, which is what this space is for. */
  action?: ReactNode;
}

const AppTopbar: FC<AppTopbarProps> = ({ title, action }) => {
  const { signOut } = useAuth();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await signOut();
      router.push("/login");
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

      <h1 className="min-w-0 flex-1 truncate font-medium text-sm">{title}</h1>

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
