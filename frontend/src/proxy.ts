import { type NextRequest, NextResponse } from "next/server";

/**
 * Sends signed out traffic to the sign in page before any of the app is rendered.
 *
 * This is an optimistic check and nothing more: it reads whether the session cookie is
 * present, never whether it is valid. Validation belongs to the backend, which signs the
 * cookie and rejects a forged or expired one on every request, and doing it here would put a
 * round trip in front of every navigation including prefetches.
 *
 * What it buys is the reason the app used to open on a screen of skeletons. The guard used to
 * be a client component that fetched `/api/auth/me` in an effect and rendered placeholders
 * until it resolved, so nothing below `/app` could be server rendered and the first paint was
 * always empty boxes. Deciding here means the server already knows whether to redirect, and
 * the page itself arrives drawn.
 *
 * A cookie that turns out to be invalid is still handled: the page renders, its first request
 * comes back 401, and the client sends the reader to `/login`. That is the rare path rather
 * than the one every load takes.
 */

/** Set by the backend on sign in. Only its presence is read here, never its contents. */
const SESSION_COOKIE = "driftline_session";

const SIGN_IN = "/login";
const AFTER_SIGN_IN = "/app/datasets";
/** Reachable signed out. Everything under `/app` is not. */
const PUBLIC_ROUTES = ["/login", "/register"];

export function proxy(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;
  const signedIn = request.cookies.has(SESSION_COOKIE);

  if (!signedIn && pathname.startsWith("/app")) {
    const url = new URL(SIGN_IN, request.url);
    // where they were headed, so signing in lands there rather than on the default screen
    if (pathname !== AFTER_SIGN_IN) url.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(url);
  }

  if (signedIn && PUBLIC_ROUTES.includes(pathname)) {
    return NextResponse.redirect(new URL(AFTER_SIGN_IN, request.url));
  }

  return NextResponse.next();
}

export const config = {
  /*
   * Everything except the API proxy, the build output and static files. `/api/*` is rewritten
   * to the backend, so running this in front of it would redirect the very requests whose 401
   * is what tells the client the session has expired.
   */
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
