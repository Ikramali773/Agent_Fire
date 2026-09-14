import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChangePasswordModal } from "./ChangePasswordModal";

const { changePassword, ApiError } = vi.hoisted(() => ({
  changePassword: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock("../api/client", () => ({ ApiError }));
vi.mock("./AuthContext", () => ({ useAuth: () => ({ changePassword }) }));

beforeEach(() => {
  changePassword.mockResolvedValue(undefined);
});

afterEach(cleanup);

async function fill(current: string, next: string, confirmation: string) {
  await userEvent.type(screen.getByLabelText("Current password"), current);
  await userEvent.type(screen.getByLabelText("New password"), next);
  await userEvent.type(screen.getByLabelText("Confirm new password"), confirmation);
  await userEvent.click(screen.getByRole("button", { name: "Change password" }));
}

describe("ChangePasswordModal", () => {
  it("changes the password and closes", async () => {
    const onClose = vi.fn();
    render(<ChangePasswordModal onClose={onClose} />);

    await fill("old-password", "new-password", "new-password");

    expect(changePassword).toHaveBeenCalledWith("old-password", "new-password");
    expect(onClose).toHaveBeenCalled();
  });

  it("catches a mistyped confirmation before sending it", async () => {
    render(<ChangePasswordModal onClose={vi.fn()} />);

    await fill("old-password", "new-password", "nwe-password");

    expect(changePassword).not.toHaveBeenCalled();
    expect((await screen.findByRole("alert")).textContent).toContain("don't match");
  });

  it("says the current password was wrong, not just that something failed", async () => {
    changePassword.mockRejectedValue(
      new ApiError('403 Forbidden: {"detail":"Current password is incorrect."}', 403),
    );
    const onClose = vi.fn();
    render(<ChangePasswordModal onClose={onClose} />);

    await fill("wrong", "new-password", "new-password");

    expect((await screen.findByRole("alert")).textContent).toContain("Current password is incorrect");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("warns that other devices will be signed out", async () => {
    // True, and the whole point when the reason for changing is that the
    // old password may have been seen - so it must not be a surprise.
    render(<ChangePasswordModal onClose={vi.fn()} />);

    const note = screen.getByText(/Every other device/).textContent ?? "";
    expect(note).toContain("signed out");
  });
});
