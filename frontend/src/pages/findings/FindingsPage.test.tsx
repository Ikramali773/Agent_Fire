import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeCaseFile } from "../../test/fixtures";
import { FindingsPage } from "./FindingsPage";
import type { RequirementReport } from "../../types";

const { getFindings } = vi.hoisted(() => ({ getFindings: vi.fn() }));

vi.mock("../../api/client", () => ({
  api: { getFindings },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

function makeReport(overrides: Partial<RequirementReport> = {}): RequirementReport {
  return {
    session_id: "s",
    evaluated: true,
    table_7_ref: "7A",
    protection_level: "HL-2",
    findings: [
      {
        code: "fire_extinguisher",
        label: "Fire extinguishers",
        status: "met",
        required: true,
        detail: "Required by Table 7A, and declared as present.",
        matched_declaration: "Fire extinguishers (12 nos.)",
      },
      {
        code: "wet_riser",
        label: "Wet riser",
        status: "not_met",
        required: true,
        detail: "Required by Table 7A and not among the systems recorded.",
        matched_declaration: null,
      },
      {
        code: "yard_hydrant",
        label: "Yard hydrant",
        status: "not_required",
        required: false,
        detail: "Table 7A does not require this.",
        matched_declaration: null,
      },
    ],
    unrecognized_declarations: [],
    met_count: 1,
    not_met_count: 1,
    unknown_count: 0,
    occupant_load: null,
    ...overrides,
  };
}

beforeEach(() => {
  getFindings.mockResolvedValue(makeReport());
});

afterEach(cleanup);

describe("FindingsPage", () => {
  it("lists each required installation with its verdict", async () => {
    render(<FindingsPage caseFile={makeCaseFile()} />);

    expect(await screen.findByText("Fire extinguishers")).toBeTruthy();
    expect(screen.getByText("Wet riser")).toBeTruthy();
  });

  it("never presents a declared system as verified or compliant", async () => {
    // The single most important thing on this page: the system knows an
    // installation was reported, not that it exists or is adequate.
    const { container } = render(<FindingsPage caseFile={makeCaseFile()} />);
    await screen.findByText("Fire extinguishers");

    expect(container.textContent).toContain("Declared, not verified");
    expect(container.textContent).not.toContain("Compliant");
  });

  it("shows what a declaration was matched to, so a match can be challenged", async () => {
    render(<FindingsPage caseFile={makeCaseFile()} />);

    expect(await screen.findByText(/Fire extinguishers \(12 nos\.\)/)).toBeTruthy();
  });

  it("separates what is required from what is not", async () => {
    render(<FindingsPage caseFile={makeCaseFile()} />);

    expect(await screen.findByText("Required for this building")).toBeTruthy();
    expect(screen.getByText("Not required for this building")).toBeTruthy();
  });

  it("surfaces recorded systems it could not recognise", async () => {
    // A system the engine did not understand is not the same as a system
    // the building does not have.
    getFindings.mockResolvedValue(makeReport({ unrecognized_declarations: ["foam deluge"] }));
    render(<FindingsPage caseFile={makeCaseFile()} />);

    expect(await screen.findByText("Recorded but not recognised")).toBeTruthy();
    expect(screen.getByText("foam deluge")).toBeTruthy();
  });

  it("leads the summary with a failure when there is one", async () => {
    render(<FindingsPage caseFile={makeCaseFile()} />);

    expect(await screen.findByText("1 not declared")).toBeTruthy();
  });

  it("says 'not known' rather than a failure when nothing was recorded", async () => {
    getFindings.mockResolvedValue(
      makeReport({ met_count: 0, not_met_count: 0, unknown_count: 4 }),
    );
    render(<FindingsPage caseFile={makeCaseFile()} />);

    expect(await screen.findByText("4 not known")).toBeTruthy();
  });

  it("explains an unclassified building rather than showing an empty table", async () => {
    getFindings.mockResolvedValue(makeReport({ evaluated: false, findings: [] }));
    render(<FindingsPage caseFile={makeCaseFile()} />);

    expect(await screen.findByText("Nothing to evaluate yet")).toBeTruthy();
  });

  it("explains that there is no project at all", () => {
    render(<FindingsPage caseFile={null} />);

    expect(screen.getByText("No active case yet")).toBeTruthy();
  });

  it("refetches when the case file changes, since findings are derived from it", async () => {
    const { rerender } = render(<FindingsPage caseFile={makeCaseFile({ updated_at: "2026-01-01T00:00:00Z" })} />);
    await screen.findByText("Fire extinguishers");

    rerender(<FindingsPage caseFile={makeCaseFile({ updated_at: "2026-01-02T00:00:00Z" })} />);

    expect(getFindings).toHaveBeenCalledTimes(2);
  });

  it("reports a failure instead of rendering an empty page", async () => {
    getFindings.mockRejectedValue(new Error("boom"));
    render(<FindingsPage caseFile={makeCaseFile()} />);

    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
