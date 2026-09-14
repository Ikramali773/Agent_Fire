import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePinnedChats } from "./usePinnedChats";

const { getPreferences, savePreferences } = vi.hoisted(() => ({
  getPreferences: vi.fn(),
  savePreferences: vi.fn(),
}));

vi.mock("../api/client", () => ({ api: { getPreferences, savePreferences } }));

beforeEach(() => {
  localStorage.clear();
  getPreferences.mockResolvedValue({ pinned_session_ids: [] });
  savePreferences.mockImplementation((prefs: { pinned_session_ids: string[] }) =>
    Promise.resolve(prefs),
  );
});

afterEach(() => vi.restoreAllMocks());

describe("usePinnedChats, signed in", () => {
  it("pins and unpins", async () => {
    const { result } = renderHook(() => usePinnedChats("user-1"));
    await waitFor(() => expect(getPreferences).toHaveBeenCalled());

    act(() => result.current.toggle("a"));
    expect(result.current.isPinned("a")).toBe(true);

    act(() => result.current.toggle("a"));
    expect(result.current.isPinned("a")).toBe(false);
  });

  it("saves pins to the account, not to this browser", async () => {
    // The whole point of the change: a pin that lives in localStorage does
    // not follow the person to another browser or a phone.
    const { result } = renderHook(() => usePinnedChats("user-1"));
    await waitFor(() => expect(getPreferences).toHaveBeenCalled());

    act(() => result.current.toggle("a"));

    await waitFor(() =>
      expect(savePreferences).toHaveBeenCalledWith({ pinned_session_ids: ["a"] }),
    );
    expect(localStorage.getItem("fire-agent-pinned-chats:user-1")).toBeNull();
  });

  it("shows pins made on another device", async () => {
    getPreferences.mockResolvedValue({ pinned_session_ids: ["from-the-phone"] });

    const { result } = renderHook(() => usePinnedChats("user-1"));

    await waitFor(() => expect(result.current.isPinned("from-the-phone")).toBe(true));
  });

  it("flips the pin immediately rather than waiting on the request", async () => {
    // Pinning is a UI convenience; making someone watch a round trip to
    // see a star fill in would be worse than reconciling a failed write.
    let resolveSave: (value: unknown) => void = () => {};
    savePreferences.mockReturnValue(new Promise((resolve) => (resolveSave = resolve)));
    const { result } = renderHook(() => usePinnedChats("user-1"));
    await waitFor(() => expect(getPreferences).toHaveBeenCalled());

    act(() => result.current.toggle("a"));

    expect(result.current.isPinned("a")).toBe(true);
    resolveSave({ pinned_session_ids: ["a"] });
  });

  it("keeps the pin visible when the save fails", async () => {
    savePreferences.mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => usePinnedChats("user-1"));
    await waitFor(() => expect(getPreferences).toHaveBeenCalled());

    act(() => result.current.toggle("a"));

    await waitFor(() => expect(savePreferences).toHaveBeenCalled());
    expect(result.current.isPinned("a")).toBe(true);
  });

  it("falls back to this browser's pins when the account cannot be reached", async () => {
    // Offline. Showing no pins at all would look like they had been lost.
    getPreferences.mockRejectedValue(new Error("offline"));
    localStorage.setItem("fire-agent-pinned-chats:user-1", '["cached"]');

    const { result } = renderHook(() => usePinnedChats("user-1"));

    await waitFor(() => expect(result.current.isPinned("cached")).toBe(true));
  });

  it("does not discard the local copy when the account cannot be reached", async () => {
    // It is the only copy there is at that moment.
    getPreferences.mockRejectedValue(new Error("offline"));
    localStorage.setItem("fire-agent-pinned-chats:user-1", '["cached"]');

    renderHook(() => usePinnedChats("user-1"));

    await waitFor(() => expect(getPreferences).toHaveBeenCalled());
    expect(localStorage.getItem("fire-agent-pinned-chats:user-1")).toBe('["cached"]');
  });
});

describe("usePinnedChats, migrating pins made before signing up", () => {
  it("merges pins this browser already held into the account", async () => {
    // Someone who pinned ten projects and then created an account should
    // not silently lose them.
    localStorage.setItem("fire-agent-pinned-chats:user-1", '["local-one","local-two"]');
    getPreferences.mockResolvedValue({ pinned_session_ids: ["on-the-account"] });

    const { result } = renderHook(() => usePinnedChats("user-1"));

    await waitFor(() =>
      expect(savePreferences).toHaveBeenCalledWith({
        pinned_session_ids: ["local-one", "local-two", "on-the-account"],
      }),
    );
    expect(result.current.count).toBe(3);
  });

  it("clears the local copy once it has been merged, so it happens once", async () => {
    localStorage.setItem("fire-agent-pinned-chats:user-1", '["local-one"]');

    renderHook(() => usePinnedChats("user-1"));

    await waitFor(() =>
      expect(localStorage.getItem("fire-agent-pinned-chats:user-1")).toBeNull(),
    );
  });

  it("does not re-save when there is nothing local to merge", async () => {
    getPreferences.mockResolvedValue({ pinned_session_ids: ["already-there"] });

    renderHook(() => usePinnedChats("user-1"));

    await waitFor(() => expect(getPreferences).toHaveBeenCalled());
    expect(savePreferences).not.toHaveBeenCalled();
  });

  it("does not duplicate a pin the account already has", async () => {
    localStorage.setItem("fire-agent-pinned-chats:user-1", '["shared"]');
    getPreferences.mockResolvedValue({ pinned_session_ids: ["shared"] });

    renderHook(() => usePinnedChats("user-1"));

    await waitFor(() => expect(getPreferences).toHaveBeenCalled());
    expect(savePreferences).not.toHaveBeenCalled();
  });
});

describe("usePinnedChats, signed out", () => {
  it("keeps pins in this browser, since there is no account to hold them", async () => {
    const { result } = renderHook(() => usePinnedChats(null));

    act(() => result.current.toggle("a"));

    expect(result.current.isPinned("a")).toBe(true);
    expect(localStorage.getItem("fire-agent-pinned-chats:anonymous")).toBe('["a"]');
    expect(getPreferences).not.toHaveBeenCalled();
    expect(savePreferences).not.toHaveBeenCalled();
  });

  it("remembers pins across a reload", () => {
    const first = renderHook(() => usePinnedChats(null));
    act(() => first.result.current.toggle("a"));

    const second = renderHook(() => usePinnedChats(null));

    expect(second.result.current.isPinned("a")).toBe(true);
  });

  it("ignores junk under the storage key instead of crashing", () => {
    // Another version of the app, or someone editing it by hand.
    localStorage.setItem("fire-agent-pinned-chats:anonymous", '{"not":"an array"}');

    const { result } = renderHook(() => usePinnedChats(null));

    expect(result.current.count).toBe(0);
  });

  it("drops non-string entries from a partly-valid list", () => {
    localStorage.setItem("fire-agent-pinned-chats:anonymous", '["a", 42, null]');

    const { result } = renderHook(() => usePinnedChats(null));

    expect(result.current.count).toBe(1);
    expect(result.current.isPinned("a")).toBe(true);
  });

  it("still works for the session when storage is unavailable", () => {
    // Private browsing: the pin holds until reload rather than throwing.
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    const { result } = renderHook(() => usePinnedChats(null));

    act(() => result.current.toggle("a"));

    expect(result.current.isPinned("a")).toBe(true);
  });
});

describe("usePinnedChats, switching accounts", () => {
  it("swaps the pin set when the signed-in account changes", async () => {
    getPreferences.mockResolvedValueOnce({ pinned_session_ids: ["mine"] });
    const { result, rerender } = renderHook(({ userId }) => usePinnedChats(userId), {
      initialProps: { userId: "user-1" as string | null },
    });
    await waitFor(() => expect(result.current.isPinned("mine")).toBe(true));

    getPreferences.mockResolvedValueOnce({ pinned_session_ids: ["theirs"] });
    rerender({ userId: "user-2" });

    await waitFor(() => expect(result.current.isPinned("theirs")).toBe(true));
    expect(result.current.isPinned("mine")).toBe(false);
  });

  it("a slow response for the previous account cannot overwrite the new one", async () => {
    // Signing out and back in as someone else on a shared machine: the
    // first request may well land after the second.
    let resolveFirst: (value: unknown) => void = () => {};
    getPreferences.mockReturnValueOnce(new Promise((resolve) => (resolveFirst = resolve)));
    const { result, rerender } = renderHook(({ userId }) => usePinnedChats(userId), {
      initialProps: { userId: "user-1" as string | null },
    });

    getPreferences.mockResolvedValueOnce({ pinned_session_ids: ["theirs"] });
    rerender({ userId: "user-2" });
    await waitFor(() => expect(result.current.isPinned("theirs")).toBe(true));

    await act(async () => {
      resolveFirst({ pinned_session_ids: ["mine"] });
    });

    expect(result.current.isPinned("mine")).toBe(false);
    expect(result.current.isPinned("theirs")).toBe(true);
  });
});
