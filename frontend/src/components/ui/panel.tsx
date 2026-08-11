import type { FC, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface PanelProps {
  title: string;
  /** Sits opposite the title: a unit, a count, a caveat about what the panel is showing. */
  aside?: ReactNode;
  /** Controls belonging to this panel, kept on the header row rather than inside the body. */
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

/**
 * A titled section with its own surface.
 *
 * Every screen was a stack of bold labels over content that sat directly on the page
 * background, so a heading was the only thing separating the scores from the plot below
 * them. This draws the boundary the heading was standing in for.
 *
 * Panels never nest. Anything that needs grouping inside one is a divider separated list,
 * which is what `panel-nesting.test.tsx` checks for.
 */
const Panel: FC<PanelProps> = ({ title, aside, action, children, className, bodyClassName }) => (
  <section
    data-slot="panel"
    className={cn(
      "flex animate-rise-in flex-col overflow-hidden rounded-xl border border-border bg-card/40",
      className,
    )}
  >
    <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-border border-b px-4 py-2.5">
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="font-medium text-sm">{title}</h2>
        {aside ? <span className="text-muted-foreground text-xs">{aside}</span> : null}
      </div>
      {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
    </header>
    <div className={cn("min-w-0 p-4", bodyClassName)}>{children}</div>
  </section>
);

export default Panel;
