import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssignmentPanel } from "./AssignmentPanel";

const { getAssignment, setAssignment, listOrganisations, listMembers, ApiError } = vi.hoisted(() => ({
  getAssignment: vi.fn(),
  setAssignment: vi.fn(),
  listOrganisations: vi.fn(),
  listMembers: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock("../../api/client", () => ({
  api: { getAssignment, setAssignment, listOrganisations, listMembers },
  ApiError,
}));

const MEMBER = {
  organisation_id: "o1",
  user_id: "u2",
  email: "colleague@example.com",
  role: "member" as const,
  added_by_user_id: "u1",
  created_at: "2026-06-01T00:00:00Z",
};

beforeEach(() => {
  getAssignment.mockResolvedValue(null);
  setAssignment.mockImplementation((_s: string, userId: string | null) =>
    Promise.resolve({
      id: 1,
      session_id: "s",
      assigned_to_user_id: userId,
      assigned_to_email: userId ? "colleague@example.com" : null,
      assigned_by_user_id: "u1",
      due_at: null,
      note: "",
      created_at: "2026-06-15T12:00:00Z",
    }),
  );
  listOrganisations.mockResolvedValue([
    { organisation: { id: "o1", name: "Team", created_by_user_id: "u1", created_at: "x" }, role: "admin", member_count: 2 },
  ]);
  listMembers.mockResolvedValue([MEMBER]);
});

afterEach(cleanup);

describe("AssignmentPanel", () => {
  it("says plainly when nobody has been asked yet", async () => {
    render(<AssignmentPanel sessionId="s" canAssign />);

    expect(await screen.findByText(/Nobody has been asked to review this yet/)).toBeTruthy();
  });

  it("assigns a colleague", async () => {
    render(<AssignmentPanel sessionId="s" canAssign />);
    await waitFor(() => expect(listMembers).toHaveBeenCalled());

    await userEvent.selectOptions(await screen.findByLabelText("Assign to"), "u2");
    await userEvent.click(screen.getByRole("button", { name: "Save assignment" }));

    await waitFor(() => expect(setAssignment).toHaveBeenCalledWith("s", "u2", null, ""));
    // The summary line, not the <option> of the same text.
    expect((await screen.findByText(/Assigned to/)).textContent).toContain("colleague@example.com");
  });

  it("sends a due date as an instant, not a bare date", async () => {
    // Midday UTC rather than midnight: a date-only deadline read back in a
    // timezone behind UTC would otherwise land on the previous day.
    render(<AssignmentPanel sessionId="s" canAssign />);
    await waitFor(() => expect(listMembers).toHaveBeenCalled());

    await userEvent.selectOptions(await screen.findByLabelText("Assign to"), "u2");
    await userEvent.type(screen.getByLabelText("Due date (optional)"), "2026-07-01");
    await userEvent.click(screen.getByRole("button", { name: "Save assignment" }));

    await waitFor(() => expect(setAssignment).toHaveBeenCalled());
    expect(setAssignment.mock.calls[0][2]).toBe("2026-07-01T12:00:00.000Z");
  });

  it("explains a refusal to assign someone who cannot see the project", async () => {
    // Assignment must never be a back door to access, and the person
    // doing it needs to know why it was refused, not just that it was.
    setAssignment.mockRejectedValue(new ApiError("422", 422));
    render(<AssignmentPanel sessionId="s" canAssign />);
    await waitFor(() => expect(listMembers).toHaveBeenCalled());

    await userEvent.selectOptions(await screen.findByLabelText("Assign to"), "u2");
    await userEvent.click(screen.getByRole("button", { name: "Save assignment" }));

    expect((await screen.findByRole("alert")).textContent).toContain("can't see this project");
  });

  it("never claims a due date is enforced", async () => {
    // A compliance tool that implied it acted on deadlines would be
    // making a promise it does not keep.
    render(<AssignmentPanel sessionId="s" canAssign />);

    const note = (await screen.findByText(/A due date is a note/)).textContent ?? "";
    expect(note).toContain("Nothing here enforces it");
  });

  it("offers no controls to someone who cannot assign", async () => {
    render(<AssignmentPanel sessionId="s" canAssign={false} />);

    expect(await screen.findByText(/Only this project's owner/)).toBeTruthy();
    expect(screen.queryByLabelText("Assign to")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save assignment" })).toBeNull();
  });

  it("distinguishes never-assigned from explicitly unassigned", async () => {
    // The backend records unassigning as its own row; the panel has to
    // reflect that rather than collapsing both to "nobody".
    getAssignment.mockResolvedValue({
      id: 2,
      session_id: "s",
      assigned_to_user_id: null,
      assigned_to_email: null,
      assigned_by_user_id: "u1",
      due_at: null,
      note: "",
      created_at: "2026-06-15T12:00:00Z",
    });
    render(<AssignmentPanel sessionId="s" canAssign />);

    expect(await screen.findByText("Explicitly unassigned.")).toBeTruthy();
  });
});
