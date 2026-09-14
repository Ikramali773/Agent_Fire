import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReviewDetail } from "./ReviewDetail";
import type { ReviewState } from "../../types";

const { getReview, recordReview, downloadHandoff, listShares } = vi.hoisted(() => ({
  getReview: vi.fn(),
  recordReview: vi.fn(),
  downloadHandoff: vi.fn(),
  listShares: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  api: {
    getReview,
    recordReview,
    downloadHandoff,
    listShares,
    shareCaseFile: vi.fn(),
    revokeShare: vi.fn(),
    listInvites: vi.fn(() => Promise.resolve([])),
    createInvite: vi.fn(),
    revokeInvite: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

function makeState(overrides: Partial<ReviewState> = {}): ReviewState {
  return {
    session_id: "s",
    project_name: "St Mary Hospital",
    requires_review: true,
    reasons: [{ code: "mandatory_occupancy", detail: "Institutional occupancy carries a mandatory flag." }],
    status: "needs_review",
    events: [],
    flagged_at: "2026-06-15T12:00:00Z",
    can_record_verdict: true,
    ...overrides,
  };
}

beforeEach(() => {
  getReview.mockResolvedValue(makeState());
  recordReview.mockImplementation((_id: string, status: string, note: string) =>
    Promise.resolve(
      makeState({
        status: status as ReviewState["status"],
        events: [
          {
            id: 1,
            session_id: "s",
            status: status as ReviewState["status"],
            note,
            actor_user_id: "u1",
            actor_email: "reviewer@example.com",
            created_at: "2026-06-15T13:00:00Z",
          },
        ],
      }),
    ),
  );
  listShares.mockResolvedValue([]);
  downloadHandoff.mockResolvedValue({ blob: new Blob(["x"]), filename: "handoff.pdf" });
});

afterEach(cleanup);

describe("ReviewDetail", () => {
  it("explains why the engine flagged the case, in plain words and in full", async () => {
    render(<ReviewDetail sessionId="s" canShare onRecorded={vi.fn()} />);

    expect(await screen.findByText("Occupancy always needs an expert")).toBeTruthy();
    expect(screen.getByText(/Institutional occupancy carries a mandatory flag/)).toBeTruthy();
  });

  it("says plainly that a verdict never replaces the classification", async () => {
    // The single most important sentence on the page: this product does
    // not let a person overwrite the deterministic engine.
    render(<ReviewDetail sessionId="s" canShare onRecorded={vi.fn()} />);

    expect(await screen.findByText(/never replaces it/)).toBeTruthy();
  });

  it("records a verdict with its note", async () => {
    const onRecorded = vi.fn();
    render(<ReviewDetail sessionId="s" canShare onRecorded={onRecorded} />);
    await screen.findByLabelText("Verdict");

    await userEvent.selectOptions(screen.getByLabelText("Verdict"), "approved");
    await userEvent.type(screen.getByLabelText("Note"), "Checked the drawings.");
    await userEvent.click(screen.getByRole("button", { name: "Record verdict" }));

    await waitFor(() => expect(recordReview).toHaveBeenCalledWith("s", "approved", "Checked the drawings."));
    expect(onRecorded).toHaveBeenCalled();
  });

  it("shows the recorded verdict in the history straight away", async () => {
    render(<ReviewDetail sessionId="s" canShare onRecorded={vi.fn()} />);
    await screen.findByLabelText("Verdict");

    await userEvent.click(screen.getByRole("button", { name: "Record verdict" }));

    expect(await screen.findByText("reviewer@example.com")).toBeTruthy();
  });

  it("never offers 'needs review' as a verdict", async () => {
    // It is the derived starting state; the backend rejects it with a 422.
    render(<ReviewDetail sessionId="s" canShare onRecorded={vi.fn()} />);
    const select = await screen.findByLabelText("Verdict");

    const options = Array.from(select.querySelectorAll("option")).map((option) => option.value);
    expect(options).not.toContain("needs_review");
    expect(options).toContain("approved");
  });

  it("hides the verdict form from someone who may not record one", async () => {
    getReview.mockResolvedValue(makeState({ can_record_verdict: false }));
    render(<ReviewDetail sessionId="s" canShare={false} onRecorded={vi.fn()} />);
    await screen.findByText("Handoff pack");

    expect(screen.queryByRole("button", { name: "Record verdict" })).toBeNull();
  });

  it("hides sharing from anyone who may not share - a reviewer, or an anonymous session", async () => {
    render(<ReviewDetail sessionId="s" canShare={false} onRecorded={vi.fn()} />);
    await screen.findByText("Handoff pack");

    expect(screen.queryByText("Reviewers")).toBeNull();
  });

  it("offers sharing to the owner", async () => {
    render(<ReviewDetail sessionId="s" canShare onRecorded={vi.fn()} />);

    expect(await screen.findByText("Reviewers")).toBeTruthy();
  });

  it("is honest when the engine did not actually require review", async () => {
    getReview.mockResolvedValue(makeState({ requires_review: false, reasons: [] }));
    const { container } = render(<ReviewDetail sessionId="s" canShare onRecorded={vi.fn()} />);
    await screen.findByText("Why this needs a person");

    // The "not" is emphasised, so the sentence is split across elements.
    expect(container.textContent).toContain("did not flag this case");
  });

  it("downloads the handoff pack", async () => {
    render(<ReviewDetail sessionId="s" canShare onRecorded={vi.fn()} />);
    await screen.findByText("Handoff pack");

    await userEvent.click(screen.getByRole("button", { name: /Download PDF/ }));

    await waitFor(() => expect(downloadHandoff).toHaveBeenCalledWith("s", "pdf"));
  });

  it("reports a failed verdict instead of looking like it saved", async () => {
    recordReview.mockRejectedValue(new Error("boom"));
    render(<ReviewDetail sessionId="s" canShare onRecorded={vi.fn()} />);
    await screen.findByLabelText("Verdict");

    await userEvent.click(screen.getByRole("button", { name: "Record verdict" }));

    expect(await screen.findByRole("alert")).toBeTruthy();
  });

  it("reports a failed load instead of rendering an empty page", async () => {
    getReview.mockRejectedValue(new Error("boom"));
    render(<ReviewDetail sessionId="s" canShare onRecorded={vi.fn()} />);

    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
