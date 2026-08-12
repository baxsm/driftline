import { cookies } from "next/headers";
import type { User } from "@/lib/types";

/**
 * The signed in user, read on the server so a page can render already knowing who it is for.
 *
 * The browser cannot do this. The session cookie is `HttpOnly`, so client code has no way to
 * read it and the old provider had to ask `/api/auth/me` from an effect, which is why every
 * screen opened on placeholders. Here the cookie is forwarded to the backend as the page is
 * built, and the user is in the first paint.
 *
 * The backend is called directly rather than through the `/api` rewrite. A rewrite is a
 * browser-facing concern: it exists so the browser's requests stay first-party, and this
 * request is not made by a browser. Going through it would have the server call its own
 * public origin to reach a service it can already address.
 */

const SESSION_COOKIE = "driftline_session";
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function readSession(): Promise<User | null> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return null;

  try {
    const response = await fetch(`${BACKEND_URL}/api/auth/me`, {
      headers: { cookie: `${SESSION_COOKIE}=${token}` },
      // a session is per request state, so a cached answer would hand one reader another's
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as User;
  } catch {
    // the backend being unreachable is not the same as being signed out, but there is nothing
    // to render for either, and the page's own requests will report the real failure
    return null;
  }
}
