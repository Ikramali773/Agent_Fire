import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AcceptInviteScreen } from "./AcceptInviteScreen";
import type { User } from "../types";

const { previewInvite, acceptInvite, ApiError, useAuth } = vi.hoisted(() => ({
  previewInvite: vi.fn(),
  acceptInvite: vi.fn(),
  useAuth: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock("../api/client", () => ({ api: { previewInvite, acceptInvite }, ApiError }));
vi.mock("../auth/AuthContext", () => ({ useAuth }));
vi.mock("../auth/LoginModal", () => ({ LoginModal: () => <div role="dialog">Sign in</div> }));

const USER: User = { id: "u2", email: "consultant@example.com", created_at: "2026-06-01T00:00:00Z" };

// Two weeks out from any plausible test clock.
const FAR_FUTURE = new Date(Date.now() + 12 * 24 * 60 * 60 * 1000).toISOString();

function preview(overrides: Record<string, unknown> = {}) {
  return {
    project_name: "St Mary Hospital",
    invited_by_email: "owner@example.com",
    invited_email: "consultant@example.com",
    expires_at: FAR_FUTURE,
    already_accepted: false,
    ...overrides,
  };
}

beforeEach(() => {
  previewInvite.mockResolvedValue(preview());
  acceptInvite.mockResolvedValue({ session_id: "s1" });
  useAuth.mockReturnValue({ user: null, loading: false });
});

afterEach(cleanup);

describe("AcceptInviteScreen", () => {
  it("says what the invitation is before asking for an account", async () => {
    // Being told to sign up with no idea what for is how an invitation
    // gets closed - the preview endpoint exists for exactly this.
    render(<AcceptInviteScreen token="t" onAccepted={vi.fn()} onDismiss={vi.fn()} />);

    expect(await screen.findByText("St Mary Hospital")).toBeTruthy();
    expect(screen.getByText("owner@example.com")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("spells out the limits of what accepting grants", async () => {
    render(<AcceptInviteScreen token="t" onAccepted={vi.fn()} onDismiss={vi.fn()} />);

    const text = (await screen.findByText(/Accepting gives you read access/)).textContent ?? "";
    expect(text).toContain("not be able to edit");
    expect(text).toContain("share it onward");
  });

  it("requires an account before it will accept", async () => {
    render(<AcceptInviteScreen token="t" onAccepted={vi.fn()} onDismiss={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "Sign in or create an account" }));

    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(acceptInvite).not.toHaveBeenCalled();
  });

  it("accepts as the signed-in account and opens the project", async () => {
    useAuth.mockReturnValue({ user: USER, loading: false });
    const onAccepted = vi.fn();
    render(<AcceptInviteScreen token="t" onAccepted={onAccepted} onDismiss={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "Accept and open the project" }));

    expect(acceptInvite).toHaveBeenCalledWith("t");
    expect(onAccepted).toHaveBeenCalledWith("s1");
  });

  it("names the account it is about to attach the project to", async () => {
    // A consultant with two accounts needs to see which one they are
    // accepting with before they click, not afterwards.
    useAuth.mockReturnValue({ user: { ...USER, email: "other@example.com" }, loading: false });
    render(<AcceptInviteScreen token="t" onAccepted={vi.fn()} onDismiss={vi.fn()} />);

    expect((await screen.findByText(/You're signed in as/)).textContent).toContain("other@example.com");
  });

  it("explains a dead link instead of showing an empty form", async () => {
    previewInvite.mockRejectedValue(new ApiError("404 Not Found: {}", 404));
    render(<AcceptInviteScreen token="t" onAccepted={vi.fn()} onDismiss={vi.fn()} />);

    expect(await screen.findByText("That invitation didn't work")).toBeTruthy();
    expect(screen.getByText(/Invitations expire after two weeks/)).toBeTruthy();
  });

  it("does not offer to accept an invitation that is already used", async () => {
    previewInvite.mockResolvedValue(preview({ already_accepted: true }));
    useAuth.mockReturnValue({ user: USER, loading: false });
    render(<AcceptInviteScreen token="t" onAccepted={vi.fn()} onDismiss={vi.fn()} />);

    expect(await screen.findByText("Already accepted")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Accept and open the project" })).toBeNull();
  });

  it("does not offer to accept an expired invitation", async () => {
    previewInvite.mockResolvedValue(preview({ expires_at: "2020-01-01T00:00:00Z" }));
    useAuth.mockReturnValue({ user: USER, loading: false });
    render(<AcceptInviteScreen token="t" onAccepted={vi.fn()} onDismiss={vi.fn()} />);

    expect(await screen.findByText("This link has expired.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Accept and open the project" })).toBeNull();
  });

  it("reports a refused acceptance instead of looking like it worked", async () => {
    useAuth.mockReturnValue({ user: USER, loading: false });
    acceptInvite.mockRejectedValue(
      new ApiError('400 Bad Request: {"detail":"This invitation has already been used, or it has expired."}', 400),
    );
    const onAccepted = vi.fn();
    render(<AcceptInviteScreen token="t" onAccepted={onAccepted} onDismiss={vi.fn()} />);

    await userEvent.click(await screen.findByRole("button", { name: "Accept and open the project" }));

    expect((await screen.findByRole("alert")).textContent).toContain("already been used");
    expect(onAccepted).not.toHaveBeenCalled();
  });
});
