import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePinnedChats } from "./usePinnedChats";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("usePinnedChats", () => {
  it("pins and unpins", () => {
    const { result } = renderHook(() => usePinnedChats("user-1"));

    act(() => result.current.toggle("a"));
    expect(result.current.isPinned("a")).toBe(true);

    act(() => result.current.toggle("a"));
    expect(result.current.isPinned("a")).toBe(false);
  });

  it("remembers pins across a reload", () => {
    const first = renderHook(() => usePinnedChats("user-1"));
    act(() => first.result.current.toggle("a"));

    const second = renderHook(() => usePinnedChats("user-1"));

    expect(second.result.current.isPinned("a")).toBe(true);
  });

  it("keeps two accounts' pins apart on a shared machine", () => {
    const mine = renderHook(() => usePinnedChats("user-1"));
    act(() => mine.result.current.toggle("a"));

    const theirs = renderHook(() => usePinnedChats("user-2"));

    expect(theirs.result.current.isPinned("a")).toBe(false);
  });

  it("swaps the pin set when the signed-in account changes", () => {
    const { result, rerender } = renderHook(({ userId }) => usePinnedChats(userId), {
      initialProps: { userId: "user-1" as string | null },
    });
    act(() => result.current.toggle("a"));

    rerender({ userId: "user-2" });

    expect(result.current.isPinned("a")).toBe(false);
  });

  it("ignores junk under the storage key instead of crashing", () => {
    // Another version of the app, or someone editing it by hand.
    localStorage.setItem("fire-agent-pinned-chats:user-1", '{"not":"an array"}');

    const { result } = renderHook(() => usePinnedChats("user-1"));

    expect(result.current.count).toBe(0);
  });

  it("drops non-string entries from a partly-valid list", () => {
    localStorage.setItem("fire-agent-pinned-chats:user-1", '["a", 42, null]');

    const { result } = renderHook(() => usePinnedChats("user-1"));

    expect(result.current.count).toBe(1);
    expect(result.current.isPinned("a")).toBe(true);
  });

  it("still works for the session when storage is unavailable", () => {
    // Private browsing: the pin holds until reload rather than throwing.
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    const { result } = renderHook(() => usePinnedChats("user-1"));

    act(() => result.current.toggle("a"));

    expect(result.current.isPinned("a")).toBe(true);
  });
});
