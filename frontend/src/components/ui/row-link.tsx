import Link from "next/link";
import type { FC, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface RowLinkProps {
  href: string;
  /** Read out in place of the row's own text, which is a paragraph of metadata. */
  label: string;
  children: ReactNode;
  className?: string;
  selected?: boolean;
}

/**
 * A list row where the whole surface navigates.
 *
 * The rows used to carry a hover highlight with only their title linked, so the row lit up
 * under the pointer and then did nothing when clicked.
 *
 * The target is a real anchor stretched over the row with a pseudo element, rather than a
 * click handler pushing a route. It costs nothing and it keeps what an anchor already does:
 * middle click and ctrl click open a new tab, the status bar shows where the row goes, and
 * Enter works without a key handler. A div with `onClick` has none of that.
 *
 * Controls sitting on the row stay above the overlay on their own stacking context, so a
 * delete button or a checkbox is pressed rather than navigated through.
 */
const RowLink: FC<RowLinkProps> = ({ href, label, children, className, selected }) => (
  <div
    data-selected={selected ? "" : undefined}
    className={cn(
      "relative isolate transition-colors duration-(--motion-quick)",
      "hover:bg-muted/50 has-[a:focus-visible]:bg-muted/50",
      "data-selected:bg-muted/60",
      className,
    )}
  >
    <Link
      href={href}
      aria-label={label}
      className={cn(
        "absolute inset-0 z-0 rounded-[inherit] outline-none",
        "focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset",
      )}
    />
    {children}
  </div>
);

export default RowLink;
