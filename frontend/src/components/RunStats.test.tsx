import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunStats } from "@/components/RunStats";
import type { Run } from "@/types";

function run(overrides: Partial<Run> = {}): Run {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    repository_url: "https://github.com/example/repo",
    status: "completed",
    error: null,
    model: "gemini-flash-latest",
    input_tokens: 30001,
    output_tokens: 352,
    cost_usd: "0.00988030",
    truncated: false,
    created_at: "2026-01-01T00:00:00Z",
    findings: [],
    ...overrides,
  };
}

describe("RunStats", () => {
  it("shows a sub-cent cost at full precision", () => {
    // Rounding to two decimals would print $0.00, which reads as free rather
    // than cheap. Most runs cost a fraction of a cent.
    render(<RunStats run={run({ cost_usd: "0.00988030" })} />);

    expect(screen.getByText("$0.009880")).toBeInTheDocument();
  });

  it("shows a larger cost in ordinary money", () => {
    render(<RunStats run={run({ cost_usd: "1.23456" })} />);

    expect(screen.getByText("$1.23")).toBeInTheDocument();
  });

  it("shows a free run as zero rather than a long decimal", () => {
    render(<RunStats run={run({ cost_usd: "0" })} />);

    expect(screen.getByText("$0.00")).toBeInTheDocument();
  });

  it("groups large token counts so they can be read at a glance", () => {
    render(<RunStats run={run({ input_tokens: 1234567 })} />);

    expect(screen.getByText("1,234,567")).toBeInTheDocument();
  });

  it("reports how many findings the run produced", () => {
    const findings = [
      {
        auditor: "dead_code",
        category: "unused_module",
        file_path: "a.py",
        line: null,
        severity: "low" as const,
        summary: "s",
        evidence: "e",
      },
    ];

    render(<RunStats run={run({ findings })} />);

    expect(screen.getByText("Findings").nextSibling).toHaveTextContent("1");
  });
});
