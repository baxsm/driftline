import type { NextConfig } from "next";

/**
 * The API is proxied through this app rather than called across origins.
 *
 * Backend and frontend deploy as separate services on separate domains. A session cookie is
 * `SameSite=Lax`, which browsers do not send on a cross-site request, so calling the backend
 * directly from the browser would authenticate in development, where both sides are
 * `localhost`, and silently stop working once deployed. The failure looks like being logged
 * out at random rather than like a configuration error.
 *
 * Rewriting `/api/*` to the backend keeps every request first-party: the browser only ever
 * talks to this origin, so the cookie is same-site by construction and needs no `SameSite=None`
 * relaxation. It also means the backend does not have to allow a browser origin through CORS at
 * all, because the proxied request is server to server.
 */
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // the floating dev badge sits over the viewer's reset control and leaks into screenshots
  devIndicators: false,

  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
