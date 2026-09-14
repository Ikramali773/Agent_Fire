import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useConversationSearch } from "./useConversationSearch";

const { searchProjects } = vi.hoisted(() => ({ searchProjects: vi.fn() }));
vi.mock("../api/client", () => ({ api: { searchProjects } }));

function hit(overrides: Record<string, unknown> = {}) {
  return {
    session_id: "s1",
    project_name: "Tower B",
    matched_in: "conversation",
    snippet: "…we discussed the atrium…",
    updated_at: "2026-06-15T12:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  searchProjects.mockResolvedValue([hit()]);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function settle() {
  // Fake timers plus React state: advancing the debounce is not enough on
  // its own, the resulting setState has to be flushed inside act().
  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });
}

describe("useConversationSearch", () => {
  it("finds projects by what was said in them", async () => {
    const { result } = renderHook(() => useConversationSearch("atrium", new Set()));

    await settle();

    expect(result.current).toHaveLength(1);
    expect(result.current[0].snippet).toContain("atrium");
  });

  it("does not ask the server on every keystroke", async () => {
    // A query per character, for results the local title match already
    // answers instantly.
    const { rerender } = renderHook(({ q }) => useConversationSearch(q, new Set()), {
      initialProps: { q: "a" },
    });
    rerender({ q: "at" });
    rerender({ q: "atr" });
    rerender({ q: "atrium" });

    await settle();

    expect(searchProjects).toHaveBeenCalledTimes(1);
    expect(searchProjects).toHaveBeenCalledWith("atrium");
  });

  it("does not ask at all below two characters", async () => {
    // The server refuses anyway - every project would match.
    renderHook(() => useConversationSearch("a", new Set()));

    await settle();

    expect(searchProjects).not.toHaveBeenCalled();
  });

  it("drops projects the title match already found", async () => {
    // Otherwise a project appears twice under two headings.
    const { result } = renderHook(() => useConversationSearch("atrium", new Set(["s1"])));

    await settle();

    expect(result.current).toEqual([]);
  });

  it("ignores name matches, which the rail shows already", async () => {
    searchProjects.mockResolvedValue([hit({ matched_in: "name", session_id: "s2" })]);
    const { result } = renderHook(() => useConversationSearch("atrium", new Set()));

    await settle();

    expect(result.current).toEqual([]);
  });

  it("shows nothing rather than an error when the request fails", async () => {
    // The local title match still works; an error in a sidebar helps
    // nobody.
    searchProjects.mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useConversationSearch("atrium", new Set()));

    await settle();

    expect(result.current).toEqual([]);
  });

  it("clears results when the query is emptied", async () => {
    const { result, rerender } = renderHook(({ q }) => useConversationSearch(q, new Set()), {
      initialProps: { q: "atrium" },
    });
    await settle();
    expect(result.current).toHaveLength(1);

    rerender({ q: "" });

    expect(result.current).toEqual([]);
  });
});
