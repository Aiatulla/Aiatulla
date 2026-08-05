import type { CreateRunBody, Run, RunDiff, RunSummary } from "@/types";

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

/** Header the backend reads the caller's own model key from. */
export const KEY_HEADER = "X-LLM-Key";

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
    throw new ApiError(response.status, await readErrorMessage(response));
  }

  return (await response.json()) as T;
}

/** Pull a readable message out of an error response, whatever shape it has. */
async function readErrorMessage(response: Response): Promise<string> {
  const body = await response.text();
  try {
    const parsed = JSON.parse(body) as { detail?: string };
    return parsed.detail ?? body;
  } catch {
    // Not every error response is JSON, so fall back to the raw text.
    return body;
  }
}

/**
 * Start an audit.
 *
 * The key is the caller's own and is passed per request. It is never stored by
 * this app: it lives in React state for as long as the tab is open and is gone
 * on refresh.
 */
export function createRun(body: CreateRunBody, apiKey: string): Promise<Run> {
  return apiFetch<Run>("/runs", {
    method: "POST",
    headers: { [KEY_HEADER]: apiKey },
    body: JSON.stringify(body),
  });
}

/** Fetch one run and its findings. Needs no key: a run holds no secrets. */
export function getRun(runId: string): Promise<Run> {
  return apiFetch<Run>(`/runs/${runId}`);
}

/** Compare a run against the previous completed run of the same repository. */
export function getRunDiff(runId: string): Promise<RunDiff> {
  return apiFetch<RunDiff>(`/runs/${runId}/diff`);
}

/** Every run of one repository, newest first. */
export function getRepositoryHistory(slug: string): Promise<RunSummary[]> {
  return apiFetch<RunSummary[]>(`/repos/${slug}/history`);
}

/** Websocket URL for a run's live progress. */
export function runProgressUrl(runId: string): string {
  const base = API_BASE.replace(/^http/, "ws");
  return `${base}${API_PREFIX}/runs/${runId}/progress`;
}
