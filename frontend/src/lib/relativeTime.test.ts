import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { parseApiTimestamp, relativeTime } from "./relativeTime";

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

describe("parseApiTimestamp", () => {
  it("reads a timestamp with no offset as UTC, not local time", () => {
    // The browser would otherwise parse this as LOCAL time, so a change
    // made seconds ago read as hours ago outside UTC. Rows written before
    // the backend started emitting an offset still look like this.
    expect(parseApiTimestamp("2026-06-15T12:00:00").toISOString()).toBe("2026-06-15T12:00:00.000Z");
  });

  it("keeps sub-second precision on a naive timestamp", () => {
    expect(parseApiTimestamp("2026-06-15T12:00:00.123456").toISOString()).toBe("2026-06-15T12:00:00.123Z");
  });

  it("leaves an explicit Z alone", () => {
    expect(parseApiTimestamp("2026-06-15T12:00:00Z").toISOString()).toBe("2026-06-15T12:00:00.000Z");
  });

  it("respects a real offset instead of overriding it", () => {
    expect(parseApiTimestamp("2026-06-15T17:30:00+05:30").toISOString()).toBe("2026-06-15T12:00:00.000Z");
    expect(parseApiTimestamp("2026-06-15T08:00:00-04:00").toISOString()).toBe("2026-06-15T12:00:00.000Z");
  });
});

describe("relativeTime with a naive timestamp", () => {
  it("says 'just now' for a UTC-naive timestamp of right now", () => {
    // The regression this whole fix exists for.
    expect(relativeTime(NOW.toISOString().replace("Z", ""))).toBe("just now");
  });
});
