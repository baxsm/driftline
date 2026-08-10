export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
 * A blocked cross-origin request and a stopped server both surface as the same thrown fetch,
 * with no detail the client can read. The message names both, because the second one is easy
 * to miss when the backend is plainly running.
 */
const NETWORK_MESSAGE =
  "Could not reach the server. Check that the backend is running and that this origin is in its CORS_ORIGINS.";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
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
