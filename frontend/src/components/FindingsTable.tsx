import { SeverityBadge } from "@/components/Badge";
import type { Finding, Severity } from "@/types";

// Worst first. A table sorted by whatever order the auditors happened to finish
// in buries a critical finding under a pile of low ones.
const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

export function FindingsTable({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return (
      <p className="text-body-sm text-ink-subtle">
        No findings. For a completed run that means the auditors looked and found
        nothing.
      </p>
    );
  }

  const sorted = [...findings].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  );

  return (
    // Wide tables scroll inside their own container so the page body never
    // scrolls sideways on a narrow screen.
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-body-sm">
        <thead>
          <tr className="border-b border-hairline text-left text-eyebrow uppercase text-ink-subtle">
            <th className="py-xs pr-md font-normal">Severity</th>
            <th className="py-xs pr-md font-normal">Auditor</th>
            <th className="py-xs pr-md font-normal">Category</th>
            <th className="py-xs pr-md font-normal">File</th>
            <th className="py-xs font-normal">Summary</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((finding, index) => (
            <tr
              key={`${finding.auditor}-${finding.category}-${finding.file_path}-${index}`}
              className="border-b border-hairline-tertiary align-top hover:bg-row-hover"
            >
              <td className="py-sm pr-md">
                <SeverityBadge severity={finding.severity} />
              </td>
              <td className="py-sm pr-md text-ink-subtle">{finding.auditor}</td>
              <td className="py-sm pr-md font-mono text-mono text-ink-muted">
                {finding.category}
              </td>
              <td className="py-sm pr-md font-mono text-mono text-ink">
                {finding.file_path}
                {finding.line !== null && (
                  <span className="text-ink-subtle">:{finding.line}</span>
                )}
              </td>
              <td className="py-sm text-ink-muted">{finding.summary}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
