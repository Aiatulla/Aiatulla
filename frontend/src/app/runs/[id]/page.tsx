"use client";

import Link from "next/link";
import { use } from "react";

import { FindingsTable } from "@/components/FindingsTable";
import { RunStats } from "@/components/RunStats";
import { useRunProgress } from "@/lib/useRunProgress";
import type { Run, RunStatus } from "@/types";

const STATUS_COLOR: Record<RunStatus, string> = {
  pending: "text-ink-subtle",
  running: "text-severity-low",
  completed: "text-success",
  failed: "text-severity-critical",
};

// Next 15 hands params over as a promise, unwrapped with use(). Next 14 passed a
// plain object, and getting this wrong is invisible to typecheck: the annotation
// is simply believed, and every request then fails at runtime.
export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { run, error } = useRunProgress(id);

  if (error !== null) {
    return <Shell>{<p className="text-body text-severity-critical">{error}</p>}</Shell>;
  }

  if (run === null) {
    return <Shell>{<p className="text-body text-ink-subtle">Loading run...</p>}</Shell>;
  }

  return (
    <Shell>
      <p className="text-eyebrow uppercase text-ink-subtle">Run</p>
      <h1 className="mt-sm break-all text-headline text-ink">{run.repository_url}</h1>

      <p className={`mt-xs text-body-sm ${STATUS_COLOR[run.status]}`}>
        {run.status}
        {run.truncated && (
          <span className="text-change-new"> · stopped at the spending ceiling</span>
        )}
      </p>

      {run.error !== null && (
        <p role="alert" className="mt-md rounded-md border border-hairline bg-surface-1 p-md text-body-sm text-severity-critical">
          {run.error}
        </p>
      )}

      <div className="mt-xl rounded-lg border border-hairline bg-surface-1 p-lg">
        <RunStats run={run} />
      </div>

      <section className="mt-xl">
        <h2 className="text-card-title text-ink">Findings</h2>
        <div className="mt-md">
          <RunBody run={run} />
        </div>
      </section>

      <Link
        href={`/repos/${slugOf(run.repository_url)}`}
        className="mt-xl inline-block text-body-sm text-primary hover:text-primary-hover"
      >
        History and what changed &rarr;
      </Link>
    </Shell>
  );
}

function RunBody({ run }: { run: Run }) {
  // A run still going has nothing useful to show yet, and an empty table would
  // read as "nothing found" rather than "not finished".
  if (run.status === "pending" || run.status === "running") {
    return <p className="text-body-sm text-ink-subtle">Auditors are working...</p>;
  }

  // A failed run has no findings because nothing ran, not because the code is
  // clean. Showing the empty-state text here would tell someone their
  // repository passed an audit that never happened.
  if (run.status === "failed") {
    return (
      <p className="text-body-sm text-ink-subtle">
        This run did not complete, so nothing was checked. The reason is above.
      </p>
    );
  }

  return <FindingsTable findings={run.findings} />;
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto min-h-screen max-w-content px-lg py-section">{children}</main>
  );
}

/** Match backend/app/services/run_service.py repository_slug. */
function slugOf(url: string): string {
  const parsed = new URL(url);
  const path = parsed.pathname.replace(/^\/|\/$/g, "").replace(/\.git$/, "");
  return `${parsed.hostname}/${path}`.toLowerCase();
}
