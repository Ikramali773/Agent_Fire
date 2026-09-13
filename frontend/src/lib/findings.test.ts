import { describe, expect, it } from "vitest";
import { findingLabel, findingsSummaryTone, findingTone } from "./findings";

describe("findingTone", () => {
  it("does not render a declared installation as a compliance pass", () => {
    // The product knows a system was declared, not that it exists, covers
    // the right areas, or is correctly designed. A green "pass" would be
    // asserting compliance the footer on every page disclaims.
    expect(findingTone("met")).not.toBe("pass");
    expect(findingTone("met")).toBe("info");
  });

  it("treats a required-but-absent installation as a failure", () => {
    expect(findingTone("not_met")).toBe("fail");
  });

  it("keeps 'nothing recorded' visually distinct from 'missing'", () => {
    // A defect and a question must not look the same.
    expect(findingTone("unknown")).toBe("unknown");
    expect(findingTone("unknown")).not.toBe(findingTone("not_met"));
  });

  it("falls back to unknown for a status it has never seen", () => {
    expect(findingTone("something_new")).toBe("unknown");
  });
});

describe("findingLabel", () => {
  it("says 'declared', never 'met' or 'compliant'", () => {
    expect(findingLabel("met")).toBe("Declared");
    expect(findingLabel("not_met")).toBe("Not declared");
  });

  it("distinguishes not-known from not-declared", () => {
    expect(findingLabel("unknown")).toBe("Not known");
    expect(findingLabel("unknown")).not.toBe(findingLabel("not_met"));
  });
});

describe("findingsSummaryTone", () => {
  it("leads with a failure when there is one", () => {
    expect(findingsSummaryTone(1, 3)).toBe("fail");
  });

  it("falls back to unknown when things are merely unassessed", () => {
    expect(findingsSummaryTone(0, 3)).toBe("unknown");
  });

  it("never claims a clean sweep is a pass", () => {
    expect(findingsSummaryTone(0, 0)).toBe("info");
  });
});
