"use client";

import { useEffect, useState } from "react";

import { getRun, runProgressUrl } from "@/lib/api";
import type { Run } from "@/types";

const TERMINAL_STATUSES = new Set(["completed", "failed"]);

/**
 * Watch a run until it finishes.
 *
 * The websocket is the live path. If it cannot connect, this falls back to
 * fetching the run once, so a proxy that blocks websockets degrades to a static
 * result rather than an empty page.
 */
export function useRunProgress(runId: string): { run: Run | null; error: string | null } {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Guards against setting state after the component unmounts, which React
    // warns about and which leaks on fast navigation.
    let active = true;
    const socket = new WebSocket(runProgressUrl(runId));

    socket.onmessage = (event) => {
      if (!active) return;

      const payload = JSON.parse(event.data as string) as Run | { error: string };

      // Discriminated on id, not on error: a Run carries its own error field,
      // so checking for "error" would match a perfectly good failed run.
      if (!("id" in payload)) {
        setError(payload.error);
        return;
      }

      setRun(payload);
      if (TERMINAL_STATUSES.has(payload.status)) {
        socket.close();
      }
    };

    socket.onerror = () => {
      if (!active) return;
      // Not fatal: fetch the run directly so the page still shows something.
      getRun(runId)
        .then((fetched) => active && setRun(fetched))
        .catch(() => active && setError("Could not reach the backend."));
    };

    return () => {
      active = false;
      socket.close();
    };
  }, [runId]);

  return { run, error };
}
