import type { Run } from "@/types";

/**
 * Tokens and money for one run.
 *
 * The cost is shown deliberately and prominently. The audit ran on the visitor's
 * own key, so what it spent is their business, not a detail to hide.
 */
export function RunStats({ run }: { run: Run }) {
  return (
    <dl className="flex flex-wrap gap-xl">
      <Stat label="Model" value={run.model} mono />
      <Stat label="Tokens in" value={run.input_tokens.toLocaleString()} mono />
      <Stat label="Tokens out" value={run.output_tokens.toLocaleString()} mono />
      <Stat label="Cost" value={formatUsd(run.cost_usd)} mono />
      <Stat label="Findings" value={String(run.findings.length)} mono />
    </dl>
  );
}

function Stat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-eyebrow uppercase text-ink-subtle">{label}</dt>
      <dd className={`mt-xxs text-body ${mono ? "font-mono text-mono" : ""} text-ink`}>
        {value}
      </dd>
    </div>
  );
}

/**
 * Show small amounts at full precision.
 *
 * A run often costs a fraction of a cent, and rounding to two decimals would
 * display every one of them as $0.00, which reads as free rather than cheap.
 */
function formatUsd(value: string): string {
  const amount = Number(value);
  if (amount === 0) return "$0.00";
  if (amount < 0.01) return `$${amount.toFixed(6)}`;
  return `$${amount.toFixed(2)}`;
}
