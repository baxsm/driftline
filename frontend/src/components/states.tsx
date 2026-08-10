import type { FC, ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Empty and error are separate components on purpose. "No sequences yet" and "could not load
 * sequences" mean opposite things, and rendering the empty state on a failed request tells
 * the user their data is gone when the server is simply unreachable.
 */

export const LoadingRows: FC<{ rows?: number }> = ({ rows = 3 }) => (
  <div className="flex flex-col gap-2" aria-busy="true" aria-live="polite">
    <span className="sr-only">Loading</span>
    {Array.from({ length: rows }, (_, index) => `skeleton-${index}`).map((key) => (
      <Skeleton key={key} className="h-16 w-full rounded-lg" />
    ))}
  </div>
);

interface EmptyStateProps {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}

export const EmptyState: FC<EmptyStateProps> = ({ title, children, action }) => (
  <div className="flex flex-col items-start gap-3 rounded-lg border border-border border-dashed px-6 py-10">
    <h2 className="font-medium text-sm">{title}</h2>
    {children ? (
      <div className="max-w-prose text-muted-foreground text-sm leading-relaxed">{children}</div>
    ) : null}
    {action}
  </div>
);

interface ErrorStateProps {
  title: string;
  message: string;
  onRetry?: () => void;
}

export const ErrorState: FC<ErrorStateProps> = ({ title, message, onRetry }) => (
  <div
    role="alert"
    className="flex flex-col items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-8"
  >
    <h2 className="font-medium text-destructive text-sm">{title}</h2>
    <p className="max-w-prose text-muted-foreground text-sm">{message}</p>
    {onRetry ? (
      <Button variant="outline" size="sm" onClick={onRetry}>
        Try again
      </Button>
    ) : null}
  </div>
);
