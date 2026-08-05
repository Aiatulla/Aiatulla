"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createRun } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();

  // The key lives here and nowhere else. Not localStorage, not sessionStorage,
  // not a cookie: it belongs to the visitor, and this app has no business
  // keeping it after the tab closes.
  const [apiKey, setApiKey] = useState("");
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const run = await createRun({ repository_url: repositoryUrl }, apiKey);
      router.push(`/runs/${run.id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong.");
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-content flex-col justify-center px-lg py-section">
      <p className="text-eyebrow uppercase text-ink-subtle">repo-radar</p>

      <h1 className="mt-sm text-display-md text-ink">Audit a repository</h1>

      <p className="mt-md max-w-[56ch] text-body-lg text-ink-muted">
        Specialised auditors read the code in parallel, report findings through a
        typed schema, and stop at a spending ceiling. Run it twice and the second
        run tells you what changed.
      </p>

      <form onSubmit={handleSubmit} className="mt-xl max-w-[52ch]">
        <Field
          label="Repository URL"
          hint="A public repository on github.com, gitlab.com or bitbucket.org."
        >
          <input
            type="url"
            required
            value={repositoryUrl}
            onChange={(event) => setRepositoryUrl(event.target.value)}
            placeholder="https://github.com/psf/requests"
            className="w-full rounded-md border border-hairline bg-surface-1 px-sm py-xs text-body text-ink placeholder:text-ink-tertiary focus:border-hairline-strong focus:outline-none"
          />
        </Field>

        <div className="mt-lg">
          <Field
            label="Your model API key"
            hint="Anthropic, Gemini or OpenAI. Sent with this request only, never stored, and gone when you close the tab."
          >
            <input
              type="password"
              required
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="sk-ant-... / AIza... / sk-..."
              className="w-full rounded-md border border-hairline bg-surface-1 px-sm py-xs font-mono text-mono text-ink placeholder:text-ink-tertiary focus:border-hairline-strong focus:outline-none"
            />
          </Field>
        </div>

        {error !== null && (
          <p role="alert" className="mt-md text-body-sm text-severity-critical">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="mt-lg rounded-md bg-primary px-md py-xs text-button text-primary-on hover:bg-primary-hover disabled:opacity-50"
        >
          {submitting ? "Starting..." : "Start audit"}
        </button>
      </form>
    </main>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-eyebrow uppercase text-ink-subtle">{label}</span>
      <span className="mt-xxs mb-xs block text-body-sm text-ink-tertiary">{hint}</span>
      {children}
    </label>
  );
}
