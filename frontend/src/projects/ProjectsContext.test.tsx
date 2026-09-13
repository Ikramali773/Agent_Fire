import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeCaseFile } from "../test/fixtures";
import { ProjectsProvider, useProjects } from "./ProjectsContext";
import type { User } from "../types";

const { myCaseFiles, myChatTitles, deleteCaseFile, updateCaseFile } = vi.hoisted(() => ({
  myCaseFiles: vi.fn(),
  myChatTitles: vi.fn(),
  deleteCaseFile: vi.fn(),
  updateCaseFile: vi.fn(),
}));
let currentUser: User | null = null;
let authLoading = false;

vi.mock("../api/client", () => ({
  api: { myCaseFiles, myChatTitles, deleteCaseFile, updateCaseFile },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: currentUser, loading: authLoading }),
}));

const USER: User = { id: "user-1", email: "a@example.com", created_at: "2026-01-01T00:00:00Z" };

function Probe() {
  const { projects, titles, remove, upsert, rename } = useProjects();
  return (
    <div>
      <span data-testid="titles">{JSON.stringify(titles)}</span>
      <button onClick={() => void rename("a", "Renamed").catch(() => undefined)}>rename a</button>
      <ul data-testid="rows">
        {(projects ?? []).map((project) => (
          <li key={project.session_id}>{project.session_id}</li>
        ))}
      </ul>
      <span data-testid="state">{projects === null ? "null" : `len:${projects.length}`}</span>
      {/* remove() deliberately rethrows so the real caller
          (DeleteProjectDialog) can show the failure; this probe stands in
          for that caller and swallows it the same way. */}
      <button onClick={() => void remove("a").catch(() => undefined)}>remove a</button>
      <button onClick={() => upsert(makeCaseFile({ session_id: "c", updated_at: "2026-03-01T00:00:00Z" }))}>
        upsert c
      </button>
      <button onClick={() => upsert(makeCaseFile({ session_id: "b", updated_at: "2026-04-01T00:00:00Z" }))}>
        touch b
      </button>
    </div>
  );
}

function renderProbe() {
  return render(
    <ProjectsProvider>
      <Probe />
    </ProjectsProvider>,
  );
}

const ids = () => screen.getAllByRole("listitem").map((node) => node.textContent);

beforeEach(() => {
  currentUser = USER;
  authLoading = false;
  myCaseFiles.mockResolvedValue([
    makeCaseFile({ session_id: "a", updated_at: "2026-01-01T00:00:00Z" }),
    makeCaseFile({ session_id: "b", updated_at: "2026-02-01T00:00:00Z" }),
  ]);
  myChatTitles.mockResolvedValue([]);
  deleteCaseFile.mockResolvedValue(undefined);
  updateCaseFile.mockImplementation((sessionId: string, updates: Record<string, unknown>) =>
    Promise.resolve(makeCaseFile({ session_id: sessionId, ...updates })),
  );
});

afterEach(cleanup);

describe("ProjectsProvider", () => {
  it("loads the account's projects newest-updated first", async () => {
    renderProbe();

    await waitFor(() => expect(ids()).toEqual(["b", "a"]));
  });

  it("holds null and fetches nothing while signed out", async () => {
    currentUser = null;
    renderProbe();

    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("null"));
    expect(myCaseFiles).not.toHaveBeenCalled();
  });

  it("waits for auth to settle before fetching", async () => {
    // Fetching before the token is applied would 401 and look to the user
    // like their projects had vanished.
    authLoading = true;
    renderProbe();

    await act(async () => {});
    expect(myCaseFiles).not.toHaveBeenCalled();
  });

  it("drops a project locally once the server delete succeeds", async () => {
    renderProbe();
    await waitFor(() => expect(ids()).toEqual(["b", "a"]));

    await userEvent.click(screen.getByRole("button", { name: "remove a" }));

    await waitFor(() => expect(ids()).toEqual(["b"]));
    expect(deleteCaseFile).toHaveBeenCalledWith("a");
  });

  it("keeps the project listed when the delete is rejected", async () => {
    // The row must not disappear optimistically - the dialog reports the
    // failure and the project is still there.
    deleteCaseFile.mockRejectedValue(new Error("nope"));
    renderProbe();
    await waitFor(() => expect(ids()).toEqual(["b", "a"]));

    await userEvent.click(screen.getByRole("button", { name: "remove a" }));

    await act(async () => {});
    expect(ids()).toEqual(["b", "a"]);
  });

  it("inserts a newly created project into the list", async () => {
    renderProbe();
    await waitFor(() => expect(ids()).toEqual(["b", "a"]));

    await userEvent.click(screen.getByRole("button", { name: "upsert c" }));

    await waitFor(() => expect(ids()).toEqual(["c", "b", "a"]));
  });

  it("re-sorts an existing project to the top when it is touched", async () => {
    // This is what moves the live conversation up the rail as it is used,
    // rather than leaving a stale duplicate behind.
    renderProbe();
    await waitFor(() => expect(ids()).toEqual(["b", "a"]));

    await userEvent.click(screen.getByRole("button", { name: "upsert c" }));
    await waitFor(() => expect(ids()).toEqual(["c", "b", "a"]));
    await userEvent.click(screen.getByRole("button", { name: "touch b" }));

    await waitFor(() => expect(ids()).toEqual(["b", "c", "a"]));
  });

  it("loads chat titles alongside the projects", async () => {
    // Fetched together on purpose: a project list without its titles
    // renders "Untitled project" rows that shift under the reader a
    // moment later.
    myChatTitles.mockResolvedValue([{ session_id: "a", title: "A hospital in Pune" }]);
    renderProbe();

    await waitFor(() =>
      expect(screen.getByTestId("titles").textContent).toBe('{"a":"A hospital in Pune"}'),
    );
  });

  it("forgets a deleted project's title too", async () => {
    myChatTitles.mockResolvedValue([{ session_id: "a", title: "A hospital in Pune" }]);
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("titles").textContent).toContain("Pune"));

    await userEvent.click(screen.getByRole("button", { name: "remove a" }));

    await waitFor(() => expect(screen.getByTestId("titles").textContent).toBe("{}"));
  });

  it("renames a project in place without reordering the list", async () => {
    renderProbe();
    await waitFor(() => expect(ids()).toEqual(["b", "a"]));

    await userEvent.click(screen.getByRole("button", { name: "rename a" }));

    await waitFor(() => expect(updateCaseFile).toHaveBeenCalledWith("a", { project_name: "Renamed" }));
    expect(ids()).toEqual(["b", "a"]);
  });

  it("surfaces a load failure instead of pretending the account has no projects", async () => {
    myCaseFiles.mockRejectedValue(new Error("boom"));
    renderProbe();

    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("null"));
  });
});
