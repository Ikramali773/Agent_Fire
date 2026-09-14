import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ResetPasswordScreen } from "./ResetPasswordScreen";

const { confirmPasswordReset, ApiError } = vi.hoisted(() => ({
  confirmPasswordReset: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock("../api/client", () => ({ api: { confirmPasswordReset }, ApiError }));

beforeEach(() => {
  confirmPasswordReset.mockResolvedValue(undefined);
});

afterEach(cleanup);

async function fill(password: string, confirmation: string) {
  await userEvent.type(screen.getByLabelText("New password"), password);
  await userEvent.type(screen.getByLabelText("Confirm new password"), confirmation);
  await userEvent.click(screen.getByRole("button", { name: "Set new password" }));
}

describe("ResetPasswordScreen", () => {
  it("sets a new password with the token from the link", async () => {
    render(<ResetPasswordScreen token="tok" onDone={vi.fn()} />);

    await fill("correct-horse", "correct-horse");

    expect(confirmPasswordReset).toHaveBeenCalledWith("tok", "correct-horse");
    expect(await screen.findByText(/Password has been changed|has been changed/)).toBeTruthy();
  });

  it("catches a mistyped confirmation before sending it", async () => {
    // Without this a typo would set the password to something nobody
    // knows, and the link is single-use - so there'd be no second chance.
    render(<ResetPasswordScreen token="tok" onDone={vi.fn()} />);

    await fill("correct-horse", "correct-hoarse");

    expect(confirmPasswordReset).not.toHaveBeenCalled();
    expect((await screen.findByRole("alert")).textContent).toContain("don't match");
  });

  it("passes on the backend's reason when the link is spent", async () => {
    // "Expired" and "already used" mean ask for a new link; a generic
    // failure would have the user retyping a password that can never work.
    confirmPasswordReset.mockRejectedValue(
      new ApiError(
        '400 Bad Request: {"detail":"This reset link is invalid, already used, or expired."}',
        400,
      ),
    );
    render(<ResetPasswordScreen token="tok" onDone={vi.fn()} />);

    await fill("correct-horse", "correct-horse");

    expect((await screen.findByRole("alert")).textContent).toContain("already used, or expired");
  });

  it("says every other session was ended, because it was", async () => {
    render(<ResetPasswordScreen token="tok" onDone={vi.fn()} />);

    await fill("correct-horse", "correct-horse");

    expect((await screen.findByText(/signed out/)).textContent).toContain("signed out");
  });
});
