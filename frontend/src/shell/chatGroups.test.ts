import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeCaseFile } from "../test/fixtures";
import { groupChatsByRecency } from "./chatGroups";

// Mid-afternoon, so "yesterday" tests aren't accidentally measuring
// elapsed hours instead of calendar days.
const NOW = new Date(2026, 5, 15, 15, 0, 0);

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => vi.useRealTimers());

function at(date: Date) {
  return makeCaseFile({ session_id: date.toISOString(), updated_at: date.toISOString() });
}

describe("groupChatsByRecency", () => {
  it("buckets by how long ago each project was touched", () => {
    const groups = groupChatsByRecency(
      [
        at(new Date(2026, 5, 15, 9, 0)),
        at(new Date(2026, 5, 14, 9, 0)),
        at(new Date(2026, 5, 11, 9, 0)),
        at(new Date(2026, 5, 1, 9, 0)),
        at(new Date(2026, 2, 1, 9, 0)),
      ],
      NOW,
    );

    expect(groups.map((group) => group.label)).toEqual([
      "Today",
      "Yesterday",
      "Previous 7 days",
      "Previous 30 days",
      "Older",
    ]);
  });

  it("counts calendar days, not elapsed hours", () => {
    // Touched at 11pm last night: barely 16 hours ago, but it is still
    // yesterday to a reader.
    const groups = groupChatsByRecency([at(new Date(2026, 5, 14, 23, 0))], NOW);

    expect(groups[0].label).toBe("Yesterday");
  });

  it("keeps several projects from the same day in one group", () => {
    const groups = groupChatsByRecency([at(new Date(2026, 5, 15, 9, 0)), at(new Date(2026, 5, 15, 8, 0))], NOW);

    expect(groups).toHaveLength(1);
    expect(groups[0].projects).toHaveLength(2);
  });

  it("drops empty buckets instead of rendering bare headings", () => {
    const groups = groupChatsByRecency([at(new Date(2026, 2, 1, 9, 0))], NOW);

    expect(groups.map((group) => group.label)).toEqual(["Older"]);
  });

  it("reads an offset-less timestamp as UTC, like everything else does", () => {
    const project = makeCaseFile({ updated_at: NOW.toISOString().replace("Z", "") });

    expect(groupChatsByRecency([project], NOW)[0].label).toBe("Today");
  });

  it("handles an empty list", () => {
    expect(groupChatsByRecency([], NOW)).toEqual([]);
  });
});
