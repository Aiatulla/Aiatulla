"use client";

import Link from "next/link";

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

// Next 14 hands params over as a plain object. Next 15 makes it a promise to be
// unwrapped with use(). Typing it as a promise here compiled and passed
// typecheck, then failed on every request with "An unsupported type was passed
// to use()", because the annotation was simply untrue.
export default function RunPage({ params }: { params: { id: string } }) {
  const { run, error } = useRunProgress(params.id);

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
