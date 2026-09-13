import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeCaseFile } from "../test/fixtures";
import { RecentChats } from "./RecentChats";
import type { CaseFile, User } from "../types";

let currentUser: User | null = { id: "user-1", email: "a@example.com", created_at: "2026-01-01T00:00:00Z" };
let projects: CaseFile[] | null = [];
let titles: Record<string, string> = {};

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ user: currentUser }),
}));

vi.mock("../auth/LoginModal", () => ({
  LoginModal: () => <div role="dialog">Sign in</div>,
}));

vi.mock("../projects/ProjectsContext", () => ({
  useProjects: () => ({ projects, titles, loading: false, error: null }),
}));

vi.mock("../projects/DeleteProjectDialog", () => ({
  DeleteProjectDialog: ({ project }: { project: CaseFile }) => <div role="dialog">Delete {project.session_id}</div>,
}));

vi.mock("../projects/RenameProjectDialog", () => ({
  RenameProjectDialog: ({ project }: { project: CaseFile }) => <div role="dialog">Rename {project.session_id}</div>,
}));

const NOW = new Date(2026, 5, 15, 15, 0, 0);

function daysAgo(days: number): string {
  return new Date(NOW.getTime() - days * 24 * 60 * 60 * 1000).toISOString();
}

function renderRail(overrides = {}) {
  const props = {
    activeSessionId: null,
    onOpenChat: vi.fn(),
    onNewChat: vi.fn(),
    onViewAll: vi.fn(),
    onDeleted: vi.fn(),
    onRenamed: vi.fn(),
    ...overrides,
  };
  render(<RecentChats {...props} />);
  return props;
}

// The row's own button, not the overflow-menu trigger beside it.
const titlesOnScreen = () =>
  Array.from(document.querySelectorAll(".ds-recent-chats__item")).map((node) => node.getAttribute("title"));

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(NOW);
  currentUser = { id: "user-1", email: "a@example.com", created_at: "2026-01-01T00:00:00Z" };
  projects = [];
  titles = {};
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

describe("RecentChats", () => {
  it("explains why there is nothing to show when signed out", () => {
    currentUser = null;
    renderRail();

    expect(screen.getByText(/to keep your chats/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /New chat/ })).toBeNull();
  });

  it("titles a chat by its first message when the project has no name", () => {
    // Otherwise a rail of fresh chats is a column of identical
    // "Untitled project" rows.
    projects = [makeCaseFile({ session_id: "a", updated_at: daysAgo(0) })];
    titles = { a: "A twelve storey hospital in Pune" };
    renderRail();

    expect(screen.getByTitle("A twelve storey hospital in Pune")).toBeTruthy();
  });

  it("prefers the project's real name over the derived title", () => {
    projects = [makeCaseFile({ session_id: "a", project_name: "Al Reem Tower", updated_at: daysAgo(0) })];
    titles = { a: "A twelve storey hospital in Pune" };
    renderRail();

    expect(screen.getByTitle("Al Reem Tower")).toBeTruthy();
  });

  it("groups chats by when they were last touched", () => {
    projects = [
      makeCaseFile({ session_id: "a", project_name: "Today one", updated_at: daysAgo(0) }),
      makeCaseFile({ session_id: "b", project_name: "Yesterday one", updated_at: daysAgo(1) }),
      makeCaseFile({ session_id: "c", project_name: "Last week one", updated_at: daysAgo(4) }),
    ];
    renderRail();

    expect(screen.getByRole("heading", { name: "Today" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Yesterday" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Previous 7 days" })).toBeTruthy();
  });

  it("opens the chat that was clicked", async () => {
    const project = makeCaseFile({ session_id: "a", project_name: "Al Reem Tower", updated_at: daysAgo(0) });
    projects = [project];
    const props = renderRail();

    await userEvent.click(screen.getByTitle("Al Reem Tower"));

    expect(props.onOpenChat).toHaveBeenCalledWith(project);
  });

  it("shows only the most recent chats, with a way to see the rest", async () => {
    projects = Array.from({ length: 12 }, (_, index) =>
      makeCaseFile({ session_id: `p${index}`, project_name: `Project ${index}`, updated_at: daysAgo(index) }),
    );
    const props = renderRail();
    expect(titlesOnScreen()).toHaveLength(8);

    await userEvent.click(screen.getByRole("button", { name: /All 12 projects/ }));

    expect(props.onViewAll).toHaveBeenCalled();
  });

  it("searches across every project, not just the ones on screen", async () => {
    // The match here is the 12th project, well past the 8 the rail shows.
    projects = Array.from({ length: 12 }, (_, index) =>
      makeCaseFile({ session_id: `p${index}`, project_name: `Project ${index}`, updated_at: daysAgo(index) }),
    );
    renderRail();

    await userEvent.type(screen.getByRole("searchbox", { name: "Search chats" }), "Project 11");

    expect(titlesOnScreen()).toHaveLength(1);
    expect(screen.getByTitle("Project 11")).toBeTruthy();
  });

  it("says so when a search matches nothing", async () => {
    projects = Array.from({ length: 12 }, (_, index) =>
      makeCaseFile({ session_id: `p${index}`, project_name: `Project ${index}`, updated_at: daysAgo(index) }),
    );
    renderRail();

    await userEvent.type(screen.getByRole("searchbox", { name: "Search chats" }), "warehouse");

    expect(screen.getByText(/No chats match/)).toBeTruthy();
  });

  it("hides the search box until there is more than a screenful to search", () => {
    projects = [makeCaseFile({ session_id: "a", project_name: "Only one", updated_at: daysAgo(0) })];
    renderRail();

    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  it("lifts a pinned chat out of the date groups and always shows it", async () => {
    projects = Array.from({ length: 12 }, (_, index) =>
      makeCaseFile({ session_id: `p${index}`, project_name: `Project ${index}`, updated_at: daysAgo(index) }),
    );
    renderRail();
    // Project 11 is old enough to be off the end of the rail.
    expect(screen.queryByTitle("Project 11")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Actions for Project 0" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Pin" }));

    expect(screen.getByRole("heading", { name: "Pinned" })).toBeTruthy();
    expect(titlesOnScreen()[0]).toContain("Project 0");
  });

  it("offers to unpin a chat that is already pinned", async () => {
    projects = [makeCaseFile({ session_id: "a", project_name: "Al Reem Tower", updated_at: daysAgo(0) })];
    renderRail();
    await userEvent.click(screen.getByRole("button", { name: "Actions for Al Reem Tower" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Pin" }));

    await userEvent.click(screen.getByRole("button", { name: "Actions for Al Reem Tower" }));

    expect(screen.getByRole("menuitem", { name: "Unpin" })).toBeTruthy();
  });

  it("opens the rename dialog from the row menu", async () => {
    projects = [makeCaseFile({ session_id: "a", project_name: "Al Reem Tower", updated_at: daysAgo(0) })];
    renderRail();

    await userEvent.click(screen.getByRole("button", { name: "Actions for Al Reem Tower" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Rename" }));

    expect(screen.getByText("Rename a")).toBeTruthy();
  });

  it("opens the delete dialog from the row menu", async () => {
    projects = [makeCaseFile({ session_id: "a", project_name: "Al Reem Tower", updated_at: daysAgo(0) })];
    renderRail();

    await userEvent.click(screen.getByRole("button", { name: "Actions for Al Reem Tower" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Delete" }));

    expect(screen.getByText("Delete a")).toBeTruthy();
  });

  it("closes the row menu on Escape rather than stranding it open", async () => {
    projects = [makeCaseFile({ session_id: "a", project_name: "Al Reem Tower", updated_at: daysAgo(0) })];
    renderRail();
    await userEvent.click(screen.getByRole("button", { name: "Actions for Al Reem Tower" }));

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("marks the open chat as current", () => {
    projects = [
      makeCaseFile({ session_id: "a", project_name: "Open one", updated_at: daysAgo(0) }),
      makeCaseFile({ session_id: "b", project_name: "Other one", updated_at: daysAgo(0) }),
    ];
    renderRail({ activeSessionId: "a" });

    expect(screen.getByTitle("Open one").getAttribute("aria-current")).toBe("true");
    expect(screen.getByTitle("Other one").getAttribute("aria-current")).toBeNull();
  });

  it("invites a signed-in account with no projects to start one", () => {
    renderRail();

    expect(screen.getByText(/No chats yet/)).toBeTruthy();
  });
});
