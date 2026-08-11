/*
 * Every request in this app goes to its own origin as `/api/...`, and `next.config.ts` rewrites
 * that to the backend.
 *
 * Calling the backend's URL directly would make every request cross-site once the two services
 * are deployed separately, and the session cookie is `SameSite=Lax`, which browsers withhold on
 * cross-site requests. That fails only in production, and it presents as being randomly logged
 * out rather than as a misconfiguration. Going through the proxy keeps the cookie first-party,
 * which is why there is no base URL constant here to prefix onto anything.
 */

export interface ApiErrorBody {
  code: string;
  message: string;
  field?: string;
}

export class ApiError extends Error {
  readonly code: string;
  readonly field?: string;
  readonly status: number;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.field = body.field;
  }
}

/**
 * Requests are proxied, so a failure here means this app could not reach the backend rather
 * than that the browser blocked it. `BACKEND_URL` is the setting that decides where it looked.
 */
const NETWORK_MESSAGE =
  "Could not reach the server. Check that the backend is running and that BACKEND_URL points at it.";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, { code: "network_error", message: NETWORK_MESSAGE });
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const parsed: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const body = (parsed as { error?: ApiErrorBody } | null)?.error;
    throw new ApiError(
      response.status,
      body ?? { code: "request_failed", message: "Something went wrong." },
    );
  }

  return parsed as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
