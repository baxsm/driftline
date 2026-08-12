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
    <div className="flex min-h-svh">
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col">{children}</div>
    </div>
  );
}
