import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReviewQueue } from "./ReviewQueue";
import type { ReviewQueueItem } from "../../types";

const { myReviewQueue } = vi.hoisted(() => ({ myReviewQueue: vi.fn() }));

vi.mock("../../api/client", () => ({
  api: { myReviewQueue },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

function item(overrides: Partial<ReviewQueueItem> = {}): ReviewQueueItem {
  return {
    session_id: "s1",
    project_name: "St Mary Hospital",
    reason_codes: ["mandatory_occupancy"],
    reason_count: 1,
    status: "needs_review",
    is_owner: true,
    updated_at: "2026-06-15T12:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  myReviewQueue.mockResolvedValue([]);
});

afterEach(cleanup);

describe("ReviewQueue", () => {
  it("shows why each case is queued, in plain words", async () => {
    myReviewQueue.mockResolvedValue([item()]);
    render(<ReviewQueue selectedSessionId={null} onSelect={vi.fn()} refreshKey={0} />);

    expect(await screen.findByText("Occupancy always needs an expert")).toBeTruthy();
  });

  it("renders the order the backend returned, without re-sorting", async () => {
    // The backend orders oldest-first on purpose; a client-side re-sort
    // would silently undo that.
    myReviewQueue.mockResolvedValue([
      item({ session_id: "old", project_name: "Oldest", updated_at: "2026-01-01T00:00:00Z" }),
      item({ session_id: "new", project_name: "Newest", updated_at: "2026-06-01T00:00:00Z" }),
    ]);
    render(<ReviewQueue selectedSessionId={null} onSelect={vi.fn()} refreshKey={0} />);
    await screen.findByText("Oldest");

    const names = Array.from(document.querySelectorAll(".ds-review-queue__item-name")).map(
      (node) => node.textContent,
    );
    expect(names).toEqual(["Oldest", "Newest"]);
  });

  it("says whether a case is yours or someone else's", async () => {
    // It decides whether you can change the facts at all.
    myReviewQueue.mockResolvedValue([item({ is_owner: false })]);
    render(<ReviewQueue selectedSessionId={null} onSelect={vi.fn()} refreshKey={0} />);

    expect(await screen.findByText(/Shared with you/)).toBeTruthy();
  });

  it("hides settled cases by default and can show them", async () => {
    render(<ReviewQueue selectedSessionId={null} onSelect={vi.fn()} refreshKey={0} />);
    await screen.findByText("Queue");
    expect(myReviewQueue).toHaveBeenLastCalledWith(false);

    await userEvent.click(screen.getByLabelText("Show settled"));

    expect(myReviewQueue).toHaveBeenLastCalledWith(true);
  });

  it("distinguishes an empty queue from an account that never had one", async () => {
    render(<ReviewQueue selectedSessionId={null} onSelect={vi.fn()} refreshKey={0} />);

    expect(await screen.findByText(/Settled ones are hidden/)).toBeTruthy();
  });

  it("selects the case that was clicked", async () => {
    const onSelect = vi.fn();
    const queued = item();
    myReviewQueue.mockResolvedValue([queued]);
    render(<ReviewQueue selectedSessionId={null} onSelect={onSelect} refreshKey={0} />);
    await screen.findByText("St Mary Hospital");

    await userEvent.click(screen.getByText("St Mary Hospital"));

    expect(onSelect).toHaveBeenCalledWith(queued);
  });

  it("marks the selected case as current", async () => {
    myReviewQueue.mockResolvedValue([item()]);
    render(<ReviewQueue selectedSessionId="s1" onSelect={vi.fn()} refreshKey={0} />);
    await screen.findByText("St Mary Hospital");

    expect(screen.getByRole("button", { current: true })).toBeTruthy();
  });

  it("reloads when the refresh key changes, so a settled case leaves", async () => {
    const { rerender } = render(<ReviewQueue selectedSessionId={null} onSelect={vi.fn()} refreshKey={0} />);
    await screen.findByText("Queue");

    rerender(<ReviewQueue selectedSessionId={null} onSelect={vi.fn()} refreshKey={1} />);

    expect(myReviewQueue).toHaveBeenCalledTimes(2);
  });

  it("reports a failure instead of looking like an empty queue", async () => {
    myReviewQueue.mockRejectedValue(new Error("boom"));
    render(<ReviewQueue selectedSessionId={null} onSelect={vi.fn()} refreshKey={0} />);

    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
