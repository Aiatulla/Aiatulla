"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import type { HealthResponse } from "@/types";

/**
 * Three states the UI must handle: still loading, backend reachable, backend down.
 * Modelling them as one union rather than separate booleans makes an impossible
 * combination (loading and errored at once) unrepresentable.
 */
type ConnectionState =
  | { kind: "loading" }
  | { kind: "connected"; health: HealthResponse }
  | { kind: "unreachable" };

/**
 * Phase 0 walking skeleton: proves the frontend can reach the backend.
 * Replaced by the repository submission form in Phase 6.
 */
export default function HomePage() {
  const [state, setState] = useState<ConnectionState>({ kind: "loading" });

  useEffect(() => {
    // Guards against setting state after the component unmounts, which React
    // warns about in development and which leaks in fast navigation.
    let active = true;

    apiFetch<HealthResponse>("/health")
      .then((health) => active && setState({ kind: "connected", health }))
      .catch(() => active && setState({ kind: "unreachable" }));

    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-content flex-col justify-center px-lg">
      <p className="text-eyebrow uppercase text-ink-subtle">Phase 0</p>

      <h1 className="mt-sm text-display-md text-ink">repo-radar</h1>

      <p className="mt-md max-w-[52ch] text-body-lg text-ink-muted">
        Multi-agent repository auditor. Parallel auditors, evaluated against golden
        fixtures, with a hard cost ceiling per run.
      </p>

      <div className="mt-xl rounded-lg border border-hairline bg-surface-1 p-lg">
        <h2 className="text-eyebrow uppercase text-ink-subtle">Backend</h2>
        <BackendStatus state={state} />
      </div>
    </main>
  );
}

function BackendStatus({ state }: { state: ConnectionState }) {
  if (state.kind === "loading") {
    return <p className="mt-xs text-body-sm text-ink-subtle">Checking...</p>;
  }

  if (state.kind === "unreachable") {
    return (
      <p className="mt-xs text-body-sm text-ink-muted">
        Not reachable. Start it with{" "}
        <code className="font-mono text-mono text-ink">
          uvicorn app.main:app --reload --port 8001
        </code>
      </p>
    );
  }

  return (
    <p className="mt-xs flex items-center gap-xs text-body-sm text-ink">
      <span aria-hidden className="h-xxs w-xxs rounded-full bg-success" />
      Connected
      <span className="font-mono text-mono text-ink-subtle">v{state.health.version}</span>
    </p>
  );
}
