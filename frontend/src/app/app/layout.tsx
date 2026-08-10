import AppSidebar from "@/components/app-sidebar";
import RequireAuth from "@/components/require-auth";

export default function AppLayout({ children }: LayoutProps<"/app">) {
  return (
    <RequireAuth>
      <div className="flex min-h-svh">
        <AppSidebar />
        <div className="flex min-w-0 flex-1 flex-col">{children}</div>
      </div>
    </RequireAuth>
  );
}
