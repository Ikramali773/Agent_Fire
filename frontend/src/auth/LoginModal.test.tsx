import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginModal } from "./LoginModal";

const { requestPasswordReset, login, signup, ApiError } = vi.hoisted(() => ({
  requestPasswordReset: vi.fn(),
  login: vi.fn(),
  signup: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock("../api/client", () => ({ api: { requestPasswordReset }, ApiError }));
vi.mock("./AuthContext", () => ({ useAuth: () => ({ login, signup }) }));

beforeEach(() => {
  requestPasswordReset.mockResolvedValue(undefined);
  login.mockResolvedValue(undefined);
  signup.mockResolvedValue(undefined);
});

afterEach(cleanup);

describe("LoginModal", () => {
  it("signs in and closes", async () => {
    const onClose = vi.fn();
    render(<LoginModal onClose={onClose} />);

    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "hunter22-long");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(login).toHaveBeenCalledWith("a@example.com", "hunter22-long");
    expect(onClose).toHaveBeenCalled();
  });

  it("asks for a reset link without asking for a password", async () => {
    render(<LoginModal onClose={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Forgot your password?" }));
    expect(screen.queryByLabelText("Password")).toBeNull();

    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));

    expect(requestPasswordReset).toHaveBeenCalledWith("a@example.com");
  });

  it("never claims the address has an account", async () => {
    // The backend answers identically whether or not the account exists,
    // precisely so this page cannot be used to ask who uses the product.
    // Wording that said "we've emailed you" would give that away again.
    render(<LoginModal onClose={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Forgot your password?" }));
    await userEvent.type(screen.getByLabelText("Email"), "stranger@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));

    const confirmation = (await screen.findByRole("status")).textContent ?? "";
    expect(confirmation).toContain("If there's an account for stranger@example.com");
    expect(confirmation).not.toMatch(/\bwe sent\b|\bwe've sent\b|\bwe emailed\b/i);
  });

  it("does not close the modal on a reset request", async () => {
    // There is nothing to go back to yet - the user still has to read the
    // confirmation and go find the link.
    const onClose = vi.fn();
    render(<LoginModal onClose={onClose} />);

    await userEvent.click(screen.getByRole("button", { name: "Forgot your password?" }));
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));

    await screen.findByRole("status");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("keeps rate limiting legible rather than dumping the raw body", async () => {
    login.mockRejectedValue(new ApiError('429 Too Many Requests: {"detail":"..."}', 429));
    render(<LoginModal onClose={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "hunter22-long");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const alert = (await screen.findByRole("alert")).textContent ?? "";
    expect(alert).toContain("Too many attempts");
    expect(alert).not.toContain("429");
  });
});
