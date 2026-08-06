import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, KEY_HEADER, apiFetch, createRun, getRun, runProgressUrl } from "@/lib/api";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("apiFetch", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends every request under the version prefix", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ok: true }));

    await apiFetch("/health");

    expect(vi.mocked(fetch).mock.calls[0][0]).toContain("/api/v1/health");
  });

  it("keeps the default headers when a caller supplies its own", async () => {
    // The original version spread options after headers, so any caller passing
    // headers silently dropped Content-Type.
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ok: true }));

    await apiFetch("/runs", { headers: { [KEY_HEADER]: "sk-ant-x" } });

    const init = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
    expect(headers[KEY_HEADER]).toBe("sk-ant-x");
  });

  it("throws ApiError carrying the status", async () => {
    // A fresh Response per call: a body can only be read once, so reusing one
    // instance makes the second call fail for the wrong reason.
    vi.mocked(fetch).mockImplementation(async () =>
      jsonResponse({ detail: "Run not found" }, 404),
    );

    await expect(apiFetch("/runs/missing")).rejects.toThrow(ApiError);
    await expect(apiFetch("/runs/missing")).rejects.toMatchObject({ status: 404 });
  });

  it("surfaces the backend's message rather than raw JSON", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: "Too many runs." }, 429));

    await expect(apiFetch("/runs")).rejects.toThrow("Too many runs.");
  });

  it("falls back to the raw body when an error is not JSON", async () => {
    // A proxy or gateway error is often HTML, and losing it entirely would
    // leave the user with a blank message.
    vi.mocked(fetch).mockResolvedValue(new Response("502 Bad Gateway", { status: 502 }));

    await expect(apiFetch("/runs")).rejects.toThrow("502 Bad Gateway");
  });

  it("sends the caller's key as a header on a new run", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: "abc" }));

    await createRun({ repository_url: "https://github.com/a/b" }, "sk-ant-secret");

    const init = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)[KEY_HEADER]).toBe("sk-ant-secret");
    // Never in the URL: URLs reach server logs, proxy logs and error traces.
    expect(String(vi.mocked(fetch).mock.calls[0][0])).not.toContain("sk-ant-secret");
  });

  it("reads a run without needing a key", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: "abc" }));

    await getRun("abc");

    const init = vi.mocked(fetch).mock.calls[0][1] as RequestInit | undefined;
    expect((init?.headers as Record<string, string>)?.[KEY_HEADER]).toBeUndefined();
  });
});

describe("runProgressUrl", () => {
  it("switches the scheme to websocket", () => {
    expect(runProgressUrl("abc")).toMatch(/^ws:\/\//);
    expect(runProgressUrl("abc")).toContain("/runs/abc/progress");
  });
});
