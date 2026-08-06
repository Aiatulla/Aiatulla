import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FindingsTable } from "@/components/FindingsTable";
import type { Finding, Severity } from "@/types";

function finding(severity: Severity, filePath: string, line: number | null = null): Finding {
  return {
    auditor: "dead_code",
    category: "unused_module",
    file_path: filePath,
    line,
    severity,
    summary: `${severity} problem`,
    evidence: "evidence",
  };
}

describe("FindingsTable", () => {
  it("orders findings worst first", () => {
    // Deliberately out of order, so passing cannot be an accident of input order.
    render(
      <FindingsTable
        findings={[
          finding("low", "low.py"),
          finding("critical", "critical.py"),
          finding("medium", "medium.py"),
          finding("high", "high.py"),
        ]}
      />,
    );

    const rows = screen.getAllByRole("row").slice(1); // drop the header
    const files = rows.map((row) => within(row).getByText(/\.py/).textContent);

    expect(files).toEqual(["critical.py", "high.py", "medium.py", "low.py"]);
  });

  it("says nothing was found rather than showing an empty table", () => {
    render(<FindingsTable findings={[]} />);

    expect(screen.getByText(/No findings/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows the line number when there is one", () => {
    render(<FindingsTable findings={[finding("high", "app.py", 42)]} />);

    expect(screen.getByText(":42")).toBeInTheDocument();
  });

  it("omits the line number when a finding covers a whole file", () => {
    render(<FindingsTable findings={[finding("high", "app.py", null)]} />);

    expect(screen.queryByText(/:\d+/)).not.toBeInTheDocument();
  });

  it("shows every finding, including duplicates of the same category and file", () => {
    render(<FindingsTable findings={[finding("high", "a.py", 1), finding("high", "a.py", 2)]} />);

    expect(screen.getAllByRole("row")).toHaveLength(3); // header plus two
  });
});
