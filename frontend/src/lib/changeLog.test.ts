import { describe, expect, it } from "vitest";
import type { FieldChange } from "../types";
import { changeFieldLabel, changeSourceLabel, describeChangeValue, groupChanges } from "./changeLog";

function makeChange(overrides: Partial<FieldChange> = {}): FieldChange {
  return {
    id: 1,
    session_id: "s",
    field: "city",
    old_value: null,
    new_value: "Ahmedabad",
    source: "user",
    actor_user_id: null,
    created_at: "2026-06-15T12:00:00Z",
    ...overrides,
  };
}

describe("changeFieldLabel", () => {
  it("uses the human label for a known field", () => {
    // formatLabel alone renders these as "Height M" and "Built Up Area Sqm".
    expect(changeFieldLabel("height_m")).toBe("Height (m)");
    expect(changeFieldLabel("built_up_area_sqm")).toBe("Built-up area (sqm)");
  });

  it("still labels a field it has never heard of", () => {
    // A new Case File field must show up in the timeline with a
    // serviceable label, not disappear from it.
    expect(changeFieldLabel("sprinkler_coverage")).toBe("Sprinkler Coverage");
  });
});

describe("changeSourceLabel", () => {
  it("says what happened rather than naming the enum", () => {
    expect(changeSourceLabel("document")).toBe("From a document");
    expect(changeSourceLabel("dialogue")).toBe("From the conversation");
  });
});

describe("describeChangeValue", () => {
  it("calls an absent value 'Not set' rather than showing null", () => {
    expect(describeChangeValue(null)).toBe("Not set");
    expect(describeChangeValue(undefined)).toBe("Not set");
    expect(describeChangeValue("")).toBe("Not set");
  });

  it("renders false and zero as real values", () => {
    expect(describeChangeValue(false)).toBe("No");
    expect(describeChangeValue(0)).toBe("0");
  });

  it("joins a list of scalars", () => {
    expect(describeChangeValue(["sprinkler", "hydrant"])).toBe("sprinkler, hydrant");
  });

  it("counts a list of structured rows instead of dumping JSON", () => {
    expect(describeChangeValue([{ floor: "Ground" }, { floor: "First" }])).toBe("2 entries");
    expect(describeChangeValue([{ floor: "Ground" }])).toBe("1 entry");
  });

  it("calls an empty list 'None', not 'Not set'", () => {
    // An emptied list is a real change from having had items in it.
    expect(describeChangeValue([])).toBe("None");
  });
});

describe("groupChanges", () => {
  it("folds fields changed together into one event", () => {
    const groups = groupChanges([
      makeChange({ id: 3, field: "city" }),
      makeChange({ id: 2, field: "state" }),
      makeChange({ id: 1, field: "height_m" }),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0].changes.map((change) => change.field)).toEqual(["city", "state", "height_m"]);
  });

  it("keeps separate events apart when the timestamp differs", () => {
    const groups = groupChanges([
      makeChange({ id: 2, created_at: "2026-06-15T12:00:01Z" }),
      makeChange({ id: 1, created_at: "2026-06-15T12:00:00Z" }),
    ]);

    expect(groups).toHaveLength(2);
  });

  it("keeps separate events apart when the source differs", () => {
    // Same instant, different origin - a document extraction and a direct
    // edit are not one event even if they land in the same second.
    const groups = groupChanges([
      makeChange({ id: 2, source: "document" }),
      makeChange({ id: 1, source: "user" }),
    ]);

    expect(groups).toHaveLength(2);
  });

  it("handles an empty log", () => {
    expect(groupChanges([])).toEqual([]);
  });
});
