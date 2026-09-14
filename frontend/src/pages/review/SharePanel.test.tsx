import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SharePanel } from "./SharePanel";

// Hoisted with the mocks: vi.mock's factory runs before module-level
// declarations, so a plain `class ApiError` above would not exist yet.
const { listShares, shareCaseFile, revokeShare, listInvites, createInvite, revokeInvite, ApiError } = vi.hoisted(() => ({
  listShares: vi.fn(),
  shareCaseFile: vi.fn(),
  revokeShare: vi.fn(),
  listInvites: vi.fn(),
  createInvite: vi.fn(),
  revokeInvite: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock("../../api/client", () => ({
  api: { listShares, shareCaseFile, revokeShare, listInvites, createInvite, revokeInvite },
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

const INVITE = {
  session_id: "s",
  invited_email: "consultant@example.com",
  invited_by_user_id: "u1",
  created_at: "2026-06-15T12:00:00Z",
  // Two weeks out from the fixture's "now", matching INVITE_TTL.
  expires_at: "2026-06-29T12:00:00Z",
  accepted_at: null,
  accepted_by_user_id: null,
  invite_url: null,
};

beforeEach(() => {
  listShares.mockResolvedValue([]);
  listInvites.mockResolvedValue([]);
  createInvite.mockResolvedValue({ ...INVITE, invite_url: "http://localhost:5173/?invite=raw-token" });
  revokeInvite.mockResolvedValue(undefined);
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

  it("offers an invite link when the address has no account", async () => {
    // Before invites existed this said "they need to sign up first",
    // which left the owner stuck: the reviewer they actually needed was
    // precisely the one without an account. Now the same dead end is a
    // one-click route out of it.
    shareCaseFile.mockRejectedValue(new ApiError("not found", 404));
    render(<SharePanel sessionId="s" />);

    await userEvent.type(screen.getByLabelText("Reviewer's email address"), "nobody@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("No account yet for nobody@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Create invite link" }));
    expect(createInvite).toHaveBeenCalledWith("s", "nobody@example.com");
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

  it("shows the invite link once, and says so", async () => {
    // The token is stored hashed, so a link that is not copied here is
    // gone for good. The panel has to be explicit about that rather than
    // letting the owner assume they can come back for it.
    render(<SharePanel sessionId="s" />);

    await userEvent.type(screen.getByLabelText("Reviewer's email address"), "consultant@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Invite by link" }));

    const status = await screen.findByRole("status");
    expect(status.textContent).toContain("shown once");
    expect(screen.getByText("http://localhost:5173/?invite=raw-token")).toBeTruthy();
  });

  it("never shows a link for an invite it did not just create", async () => {
    // Listing invites deliberately returns invite_url: null - the owner
    // sees who was invited and whether they accepted, never the credential.
    listInvites.mockResolvedValue([INVITE]);
    render(<SharePanel sessionId="s" />);

    expect(await screen.findByText("consultant@example.com")).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("button", { name: "Copy" })).toBeNull();
  });

  it("cancels a pending invitation", async () => {
    listInvites.mockResolvedValue([INVITE]);
    render(<SharePanel sessionId="s" />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Cancel the invitation to consultant@example.com" }),
    );

    await waitFor(() => expect(revokeInvite).toHaveBeenCalledWith("s", "consultant@example.com"));
  });

  it("does not list an accepted invite alongside the reviewer it created", async () => {
    // An accepted invite already shows up as a grant; listing it in both
    // places would read as two reviewers where there is one.
    listShares.mockResolvedValue([{ ...GRANT, granted_to_email: "consultant@example.com" }]);
    listInvites.mockResolvedValue([
      { ...INVITE, accepted_at: "2026-06-16T09:00:00Z", accepted_by_user_id: "u2" },
    ]);
    render(<SharePanel sessionId="s" />);

    expect(await screen.findAllByText("consultant@example.com")).toHaveLength(1);
    expect(screen.queryByText("Invited, not yet accepted")).toBeNull();
  });
});
