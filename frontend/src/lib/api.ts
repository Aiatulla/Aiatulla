/**
 * The only place the app talks to the backend.
 *
 * Components never call fetch directly. Routing every request through here means
 * base URL, headers, and error handling are defined once instead of per caller.
 */
// Port 8001, not the usual 8000, so this backend does not collide with another
// service already bound to 8000 on the development machine.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
const API_PREFIX = "/api/v1";

/** Thrown when the backend responds with a non-2xx status. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Call the backend and parse the JSON response.
 *
 * @param path Endpoint path below the version prefix, for example "/health".
 * @throws {ApiError} when the response status is not 2xx.
 */
export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${API_PREFIX}${path}`, {
    // Options spread first, then headers, so a caller passing its own headers
    // adds to the defaults instead of replacing them.
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });

  if (!response.ok) {
    // Read the body as text: an error response is not guaranteed to be JSON.
    throw new ApiError(response.status, await response.text());
  }

  return (await response.json()) as T;
}
