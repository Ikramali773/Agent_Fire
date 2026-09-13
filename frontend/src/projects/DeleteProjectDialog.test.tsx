import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeCaseFile } from "../test/fixtures";
import { DeleteProjectDialog } from "./DeleteProjectDialog";

const remove = vi.fn();

vi.mock("./ProjectsContext", () => ({
  useProjects: () => ({ remove }),
}));

vi.mock("../api/client", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

afterEach(cleanup);

function renderDialog(overrides = {}) {
  const props = { onClose: vi.fn(), onDeleted: vi.fn(), ...overrides };
  render(<DeleteProjectDialog project={makeCaseFile({ project_name: "Al Reem Tower" })} {...props} />);
  return props;
}

describe("DeleteProjectDialog", () => {
  it("names the project and says what else is deleted with it", () => {
    // The reason this isn't window.confirm: the user has to know the
    // conversation goes too, and that there is no undo.
    renderDialog();

    expect(screen.getByText("Al Reem Tower")).toBeTruthy();
    expect(screen.getByRole("dialog").textContent).toContain("chat history");
    expect(screen.getByRole("dialog").textContent).toContain("cannot be undone");
  });

  it("deletes nothing until the destructive button is pressed", async () => {
    const props = renderDialog();

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(remove).not.toHaveBeenCalled();
    expect(props.onClose).toHaveBeenCalled();
  });

  it("reports the deletion upward and closes on success", async () => {
    remove.mockResolvedValue(undefined);
    const props = renderDialog();

    await userEvent.click(screen.getByRole("button", { name: "Delete project" }));

    await waitFor(() => expect(props.onDeleted).toHaveBeenCalledWith("session-1"));
    expect(remove).toHaveBeenCalledWith("session-1");
    expect(props.onClose).toHaveBeenCalled();
  });

  it("stays open and shows the error when the delete fails", async () => {
    remove.mockRejectedValue(new Error("network down"));
    const props = renderDialog();

    await userEvent.click(screen.getByRole("button", { name: "Delete project" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(props.onClose).not.toHaveBeenCalled();
    expect(props.onDeleted).not.toHaveBeenCalled();
  });

  it("cannot be double-submitted while the request is in flight", async () => {
    remove.mockImplementation(() => new Promise(() => undefined));
    renderDialog();
    const confirm = screen.getByRole("button", { name: "Delete project" });

    await userEvent.click(confirm);
    await userEvent.click(screen.getByRole("button", { name: "Deleting…" }));

    expect(remove).toHaveBeenCalledTimes(1);
  });
});
