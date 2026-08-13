import AppSidebar from "@/components/app-sidebar";

/**
 * The app shell, rendered on the server.
 *
 * Nothing here gates on a fetch. `proxy.ts` has already turned signed out traffic away before
 * this runs, so the sidebar and the page frame are in the first paint rather than behind the
 * screen of placeholders the old client side guard rendered while it asked who the reader was.
 */
export default function AppLayout({ children }: LayoutProps<"/app">) {
  return (
    /*
     * The shell is exactly the viewport and never grows, so the sidebar and topbar stay put
     * and only the page under them scrolls. `min-h-0` is what lets the content column shrink
     * inside it: without it a flex child refuses to go below its content height, and the
     * overflow moves back out to the page.
     */
    <div className="flex h-svh overflow-hidden">
      <AppSidebar />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</div>
    </div>
  );
}
