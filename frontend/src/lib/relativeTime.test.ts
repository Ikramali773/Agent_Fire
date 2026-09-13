import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { relativeTime } from "./relativeTime";

const NOW = new Date("2026-06-15T12:00:00Z");

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

function agoBy(ms: number): string {
  return relativeTime(new Date(NOW.getTime() - ms).toISOString());
}

const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

describe("relativeTime", () => {
  it("says 'just now' under a minute", () => {
    expect(agoBy(30 * 1000)).toBe("just now");
  });

  it("picks the largest unit that fits", () => {
    expect(agoBy(5 * MINUTE)).toBe("5 minutes ago");
    expect(agoBy(3 * HOUR)).toBe("3 hours ago");
    expect(agoBy(3 * DAY)).toBe("3 days ago");
    expect(agoBy(3 * 7 * DAY)).toBe("3 weeks ago");
  });

  it("uses words where the locale has them", () => {
    // numeric: "auto" - "yesterday" reads better than "1 day ago".
    expect(agoBy(DAY)).toBe("yesterday");
  });

  it("returns an empty string for an unparseable timestamp rather than 'Invalid Date'", () => {
    expect(relativeTime("not a date")).toBe("");
  });

  it("handles a timestamp fractionally in the future without saying 'in 0 seconds'", () => {
    // Clock skew between the server's created_at and the browser is normal.
    expect(relativeTime(new Date(NOW.getTime() + 2000).toISOString())).toBe("just now");
  });
});
