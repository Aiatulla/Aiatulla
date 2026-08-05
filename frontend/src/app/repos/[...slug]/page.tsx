"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ChangeBadge, SeverityBadge } from "@/components/Badge";
import { getRepositoryHistory, getRunDiff } from "@/lib/api";
import type { RunDiff, RunSummary } from "@/types";

/**
 * History for one repository, plus what its latest run changed.
 *
 * A catch-all route because a slug contains slashes, as in
 * github.com/psf/requests.
 */
// A plain object on Next 14, a promise on Next 15. See the note in runs/[id].
export default function RepositoryPage({ params }: { params: { slug: string[] } }) {
  const repositorySlug = params.slug.join("/");

  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [diff, setDiff] = useState<RunDiff | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    getRepositoryHistory(repositorySlug)
      .then(async (history) => {
        if (!active) return;
        setRuns(history);

        // The diff belongs to the newest run, which is the one a reader cares
        // about. Older runs are reachable through their own pages.
        if (history.length > 0) {
          const latest = await getRunDiff(history[0].id);
          if (active) setDiff(latest);
        }
      })
      .catch(() => active && setError("Could not load this repository's history."));

    return () => {
      active = false;
    };
  }, [repositorySlug]);

  return (
    <main className="mx-auto min-h-screen max-w-content px-lg py-section">
      <p className="text-eyebrow uppercase text-ink-subtle">Repository</p>
      <h1 className="mt-sm break-all font-mono text-headline text-ink">{repositorySlug}</h1>

      {error !== null && <p className="mt-md text-body text-severity-critical">{error}</p>}

      {runs !== null && runs.length === 0 && (
        <p className="mt-lg text-body text-ink-subtle">
          Nothing audited yet. <Link href="/" className="text-primary">Start a run</Link>.
        </p>
      )}

      {diff !== null && (
        <section className="mt-xl">
          <h2 className="text-card-title text-ink">
            {diff.is_first_run ? "First run" : "Since the previous run"}
          </h2>

          {diff.is_first_run ? (
            <p className="mt-xs max-w-[56ch] text-body-sm text-ink-subtle">
              Nothing to compare against yet, so every finding counts as new. Run
              it again after a change and this becomes a real comparison.
            </p>
          ) : (
            <p className="mt-xs text-body-sm text-ink-muted">
              <span className="text-change-new">{diff.counts.new} new</span>
              {" · "}
              <span className="text-change-fixed">{diff.counts.fixed} fixed</span>
              {" · "}
              <span className="text-change-persisting">
                {diff.counts.persisting} still there
              </span>
            </p>
          )}

          <div className="mt-md overflow-x-auto">
            <table className="w-full border-collapse text-body-sm">
              <tbody>
                {diff.entries.map((entry, index) => (
                  <tr
                    key={`${entry.category}-${entry.file_path}-${index}`}
                    className="border-b border-hairline-tertiary align-top hover:bg-row-hover"
                  >
                    <td className="py-sm pr-md">
                      <ChangeBadge change={entry.change} />
                    </td>
                    <td className="py-sm pr-md">
                      <SeverityBadge severity={entry.severity} />
                    </td>
                    <td className="py-sm pr-md font-mono text-mono text-ink">
                      {entry.file_path}
                    </td>
                    <td className="py-sm text-ink-muted">{entry.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {runs !== null && runs.length > 0 && (
        <section className="mt-xl">
          <h2 className="text-card-title text-ink">All runs</h2>
          <ul className="mt-md">
            {runs.map((run) => (
              <li key={run.id} className="border-b border-hairline-tertiary py-sm">
                <Link
                  href={`/runs/${run.id}`}
                  className="flex flex-wrap gap-md text-body-sm text-ink-muted hover:text-ink"
                >
                  <span className="font-mono text-mono text-ink-subtle">
                    {new Date(run.created_at).toLocaleString()}
                  </span>
                  <span>{run.status}</span>
                  {run.truncated && <span className="text-change-new">truncated</span>}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
