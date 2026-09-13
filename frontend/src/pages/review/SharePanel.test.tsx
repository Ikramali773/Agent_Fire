import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SharePanel } from "./SharePanel";

// Hoisted with the mocks: vi.mock's factory runs before module-level
// declarations, so a plain `class ApiError` above would not exist yet.
const { listShares, shareCaseFile, revokeShare, ApiError } = vi.hoisted(() => ({
  listShares: vi.fn(),
  shareCaseFile: vi.fn(),
  revokeShare: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock("../../api/client", () => ({
  api: { listShares, shareCaseFile, revokeShare },
  ApiError,
}));

const GRANT = {
  id: 1,
  session_id: "s",
  granted_to_user_id: "u2",
  granted_to_email: "reviewer@example.com",
  granted_by_user_id: "u1",
  role: "reviewer" as const,
  created_at: "2026-06-15T12:00:00Z",
};

beforeEach(() => {
  listShares.mockResolvedValue([]);
  shareCaseFile.mockResolvedValue(GRANT);
  revokeShare.mockResolvedValue(undefined);
});

afterEach(cleanup);

describe("SharePanel", () => {
  it("spells out exactly what a reviewer can and cannot do", async () => {
    // The restriction is what makes the verdict worth anything, so the
    // owner should not have to guess what they just granted.
    render(<SharePanel sessionId="s" />);

    const text = (await screen.findByText(/A reviewer can read this project/)).textContent ?? "";
    expect(text).toContain("cannot edit any fact");
    expect(text).toContain("share it with anyone else");
  });

  it("shares with an address", async () => {
    render(<SharePanel sessionId="s" />);

    await userEvent.type(screen.getByLabelText("Reviewer's email address"), "reviewer@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => expect(shareCaseFile).toHaveBeenCalledWith("s", "reviewer@example.com"));
  });

  it("submits on Enter", async () => {
    render(<SharePanel sessionId="s" />);

    await userEvent.type(screen.getByLabelText("Reviewer's email address"), "reviewer@example.com{Enter}");

    await waitFor(() => expect(shareCaseFile).toHaveBeenCalled());
  });

  it("says specifically that the address has no account", async () => {
    // A generic "could not share" gives the owner nothing to act on; this
    // tells them what to ask the reviewer to do.
    shareCaseFile.mockRejectedValue(new ApiError("not found", 404));
    render(<SharePanel sessionId="s" />);

    await userEvent.type(screen.getByLabelText("Reviewer's email address"), "nobody@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      expect.stringContaining("need to sign up"),
    );
  });

  it("will not submit an empty address", async () => {
    render(<SharePanel sessionId="s" />);
    await screen.findByText(/A reviewer can read/);

    expect(screen.getByRole("button", { name: "Add" })).toHaveProperty("disabled", true);
  });

  it("lists current reviewers and removes one", async () => {
    listShares.mockResolvedValue([GRANT]);
    render(<SharePanel sessionId="s" />);
    await screen.findByText("reviewer@example.com");

    await userEvent.click(screen.getByRole("button", { name: "Remove reviewer@example.com" }));

    await waitFor(() => expect(revokeShare).toHaveBeenCalledWith("s", "u2"));
  });

  it("says when nothing is shared yet", async () => {
    render(<SharePanel sessionId="s" />);

    expect(await screen.findByText("Not shared with anyone yet.")).toBeTruthy();
  });
});
