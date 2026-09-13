import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FieldChange } from "../../types";
import { ActivityTimeline } from "./ActivityTimeline";

const { getChanges } = vi.hoisted(() => ({ getChanges: vi.fn() }));

vi.mock("../../api/client", () => ({
  api: { getChanges },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

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

beforeEach(() => {
  getChanges.mockResolvedValue([]);
});

afterEach(cleanup);

describe("ActivityTimeline", () => {
  it("shows what a field changed from and to", async () => {
    getChanges.mockResolvedValue([makeChange({ field: "height_m", old_value: 24, new_value: 68 })]);
    render(<ActivityTimeline sessionId="s" refreshKey={0} />);

    await screen.findByText("Height (m)");
    expect(screen.getByText("24")).toBeTruthy();
    expect(screen.getByText("68")).toBeTruthy();
    expect(screen.getByText("Edited directly")).toBeTruthy();
  });

  it("says a field had no previous value rather than showing null", async () => {
    getChanges.mockResolvedValue([makeChange()]);
    render(<ActivityTimeline sessionId="s" refreshKey={0} />);

    expect(await screen.findByText("Not set")).toBeTruthy();
  });

  it("folds fields set together into one event", async () => {
    getChanges.mockResolvedValue([
      makeChange({ id: 2, field: "city", new_value: "Ahmedabad" }),
      makeChange({ id: 1, field: "state", new_value: "Gujarat" }),
    ]);
    render(<ActivityTimeline sessionId="s" refreshKey={0} />);

    await screen.findByText("City");
    expect(screen.getAllByRole("listitem").filter((node) => node.className.includes("ds-activity__event"))).toHaveLength(1);
  });

  it("explains an empty history rather than rendering nothing", async () => {
    render(<ActivityTimeline sessionId="s" refreshKey={0} />);

    expect(await screen.findByText(/Nothing has changed yet/)).toBeTruthy();
  });

  it("refetches when the refresh key changes, so a fresh edit appears", async () => {
    const { rerender } = render(<ActivityTimeline sessionId="s" refreshKey={0} />);
    await waitFor(() => expect(getChanges).toHaveBeenCalledTimes(1));

    rerender(<ActivityTimeline sessionId="s" refreshKey={1} />);

    await waitFor(() => expect(getChanges).toHaveBeenCalledTimes(2));
  });

  it("refetches when the project changes", async () => {
    const { rerender } = render(<ActivityTimeline sessionId="s" refreshKey={0} />);
    await waitFor(() => expect(getChanges).toHaveBeenCalledTimes(1));

    rerender(<ActivityTimeline sessionId="other" refreshKey={0} />);

    await waitFor(() => expect(getChanges).toHaveBeenLastCalledWith("other", { limit: 25 }));
  });

  it("offers to page further back only when the first page was full", async () => {
    getChanges.mockResolvedValue([makeChange()]);
    render(<ActivityTimeline sessionId="s" refreshKey={0} />);

    await screen.findByText("City");
    expect(screen.queryByRole("button", { name: /earlier changes/i })).toBeNull();
  });

  it("pages further back from the oldest change it already holds", async () => {
    const firstPage = Array.from({ length: 25 }, (_, index) => makeChange({ id: 100 - index }));
    getChanges.mockResolvedValueOnce(firstPage).mockResolvedValueOnce([makeChange({ id: 75, new_value: "Surat" })]);
    render(<ActivityTimeline sessionId="s" refreshKey={0} />);
    await screen.findByRole("button", { name: /earlier changes/i });

    await userEvent.click(screen.getByRole("button", { name: /earlier changes/i }));

    await waitFor(() => expect(getChanges).toHaveBeenLastCalledWith("s", { limit: 25, beforeId: 76 }));
    expect(await screen.findByText("Surat")).toBeTruthy();
  });

  it("reports a failure instead of looking like an empty history", async () => {
    getChanges.mockRejectedValue(new Error("boom"));
    render(<ActivityTimeline sessionId="s" refreshKey={0} />);

    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
