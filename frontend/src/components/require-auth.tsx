"use client";

import { useRouter } from "next/navigation";
import { type FC, type ReactNode, useEffect } from "react";
import { useAuth } from "@/components/auth-provider";
import { Skeleton } from "@/components/ui/skeleton";

const RequireAuth: FC<{ children: ReactNode }> = ({ children }) => {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "signed-out") router.replace("/login");
  }, [status, router]);

  if (status !== "signed-in") {
    return (
      <div className="flex min-h-svh">
        <div className="hidden w-56 shrink-0 border-border border-r p-3 md:block">
          <Skeleton className="mb-3 h-8 w-full" />
          <Skeleton className="mb-1.5 h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-14 items-center border-border border-b px-4">
            <Skeleton className="h-4 w-40" />
          </div>
          <div className="flex flex-col gap-3 p-6">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
};

export default RequireAuth;
