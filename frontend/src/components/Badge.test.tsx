import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChangeBadge, SeverityBadge } from "@/components/Badge";
import type { Change, Severity } from "@/types";

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];
const CHANGES: Change[] = ["new", "fixed", "persisting"];

describe("SeverityBadge", () => {
  it.each(SEVERITIES)("renders %s with a colour class", (severity) => {
    render(<SeverityBadge severity={severity} />);

    // Tailwind only keeps classes it can see written out in full, so an
    // interpolated `text-severity-${severity}` would compile and then render
    // unstyled. Asserting the class is present is what catches that.
    expect(screen.getByText(severity)).toHaveClass(`text-severity-${severity}`);
  });

  it("gives each severity a distinct colour", () => {
    const classes = SEVERITIES.map((severity) => {
      const { unmount } = render(<SeverityBadge severity={severity} />);
      const found = screen.getByText(severity).className;
      unmount();
      return found;
    });

    expect(new Set(classes).size).toBe(SEVERITIES.length);
  });
});

describe("ChangeBadge", () => {
  it.each(CHANGES)("renders %s with a colour class", (change) => {
    render(<ChangeBadge change={change} />);

    expect(screen.getByText(change)).toHaveClass(`text-change-${change}`);
  });

  it("does not colour a fixed finding like a new one", () => {
    // A fixed critical and a new critical have to be distinguishable at a glance.
    const { unmount } = render(<ChangeBadge change="fixed" />);
    const fixed = screen.getByText("fixed").className;
    unmount();

    render(<ChangeBadge change="new" />);

    expect(screen.getByText("new").className).not.toBe(fixed);
  });
});
