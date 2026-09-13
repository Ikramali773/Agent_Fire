import { describe, expect, it } from "vitest";
import { makeCaseFile } from "../test/fixtures";
import { formatLabel, formatValue, normalizeClassification, projectLabel } from "./caseFileFields";

describe("normalizeClassification", () => {
  // This exists because Required<> is SHALLOW: it strips optionality from
  // CaseFile's own keys but not from the object classification_result
  // points at. Forgetting that shipped a build failure once, and the array
  // defaults below are what stop `.map()` blowing up on a live response.
  it("defaults the arrays so callers can map over them unconditionally", () => {
    const result = normalizeClassification({ table_7_ref: "", require_human_review_flag: false });

    expect(result.applicable_clauses).toEqual([]);
    expect(result.notes).toEqual([]);
  });

  it("defaults the nullable scalars to null rather than undefined", () => {
    const result = normalizeClassification({ table_7_ref: "", require_human_review_flag: false });

    expect(result.applies).toBeNull();
    expect(result.is_high_rise).toBeNull();
    expect(result.protection_level).toBeNull();
    expect(result.applicable_state_checklist_id).toBeNull();
  });

  it("passes real values through untouched", () => {
    const result = normalizeClassification({
      applies: true,
      table_7_ref: "Table 7A",
      applicable_clauses: ["3.1.11.2"],
      is_high_rise: true,
      require_human_review_flag: true,
      protection_level: "Level 2",
      notes: ["Occupant load unconfirmed"],
    });

    expect(result).toMatchObject({
      applies: true,
      table_7_ref: "Table 7A",
      applicable_clauses: ["3.1.11.2"],
      is_high_rise: true,
      require_human_review_flag: true,
      protection_level: "Level 2",
      notes: ["Occupant load unconfirmed"],
    });
  });
});

describe("projectLabel", () => {
  it("prefers the project name", () => {
    expect(projectLabel(makeCaseFile({ project_name: "Al Reem Tower", city: "Ahmedabad" }))).toBe("Al Reem Tower");
  });

  it("falls back to city and state while the project is unnamed", () => {
    expect(projectLabel(makeCaseFile({ city: "Ahmedabad", state: "Gujarat" }))).toBe("Ahmedabad, Gujarat");
  });

  it("uses whichever half of the location is known", () => {
    expect(projectLabel(makeCaseFile({ state: "Gujarat" }))).toBe("Gujarat");
  });

  it("falls back to the occupancy when there is no location either", () => {
    expect(projectLabel(makeCaseFile({ occupancy_type: "Mercantile" }))).toBe("Mercantile");
  });

  it("only says Untitled project when nothing at all is known", () => {
    expect(projectLabel(makeCaseFile())).toBe("Untitled project");
  });
});

describe("formatLabel", () => {
  it("title-cases a snake_case enum value", () => {
    expect(formatLabel("mixed_use")).toBe("Mixed Use");
  });

  it("has a fallback for a missing value", () => {
    expect(formatLabel(null)).toBe("Not yet known");
  });
});

describe("formatValue", () => {
  it("renders false rather than treating it as missing", () => {
    // A real bug class: `value || fallback` would show "Not yet known"
    // for a legitimate "No".
    expect(formatValue(false)).toBe("No");
  });

  it("renders zero rather than treating it as missing", () => {
    expect(formatValue(0)).toBe("0");
  });

  it("uses the fallback for null and undefined", () => {
    expect(formatValue(null)).toBe("Not yet known");
    expect(formatValue(undefined)).toBe("Not yet known");
  });
});
