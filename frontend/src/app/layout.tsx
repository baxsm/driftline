import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AuthProvider } from "@/components/auth-provider";
import { Toaster } from "@/components/ui/sonner";
import QueryProvider from "@/lib/query-client";
import { readSession } from "@/lib/session";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "driftline",
  description:
    "Estimate camera trajectories from video and IMU data, and measure the drift against ground truth.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // read here rather than fetched in the browser, so the app knows who it is rendering for
  // before the first paint instead of after a round trip
  const user = await readSession();

  return (
    <html
      lang="en"
      className={`dark ${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-background text-foreground">
        {/* the cache wraps auth, so signing out can clear it rather than outlive the session */}
        <QueryProvider>
          <AuthProvider user={user}>{children}</AuthProvider>
        </QueryProvider>
        {/* a confirmation that outlives the action it confirms just sits on top of the page */}
        <Toaster position="bottom-right" duration={4000} />
      </body>
    </html>
  );
}
