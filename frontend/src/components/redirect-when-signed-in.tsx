"use client";

import { useRouter } from "next/navigation";
import { type FC, type ReactNode, useEffect } from "react";
import { useAuth } from "@/components/auth-provider";

/**
 * Keeps a signed in user off the auth pages. The form still renders while the session is
 * being checked, because showing a spinner in its place makes the common case (signed out)
 * feel slower than it is.
 */
const RedirectWhenSignedIn: FC<{ children: ReactNode }> = ({ children }) => {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "signed-in") router.replace("/app/datasets");
  }, [status, router]);

  return <>{children}</>;
};

export default RedirectWhenSignedIn;
