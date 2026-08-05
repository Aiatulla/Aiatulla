import type { Change, Severity } from "@/types";

// Explicit maps rather than building a class name from a template string.
// Tailwind only keeps classes it can see written out in full, so an
// interpolated `text-severity-${severity}` would be stripped from the build.
const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "text-severity-critical",
  high: "text-severity-high",
  medium: "text-severity-medium",
  low: "text-severity-low",
  info: "text-severity-info",
};

const CHANGE_COLOR: Record<Change, string> = {
  new: "text-change-new",
  fixed: "text-change-fixed",
  persisting: "text-change-persisting",
};

function Pill({ label, color }: { label: string; color: string }) {
  return (
    <span
      className={`inline-block rounded-pill bg-surface-2 px-xs py-0 text-caption uppercase ${color}`}
    >
      {label}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Pill label={severity} color={SEVERITY_COLOR[severity]} />;
}

export function ChangeBadge({ change }: { change: Change }) {
  return <Pill label={change} color={CHANGE_COLOR[change]} />;
}
