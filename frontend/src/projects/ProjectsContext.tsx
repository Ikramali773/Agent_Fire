import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError, PROJECT_PAGE_SIZE } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { parseApiTimestamp } from "../lib/relativeTime";
import type { CaseFile } from "../types";

interface ProjectsContextValue {
  /** The loaded page of projects; null until it loads (or while signed out). */
  projects: CaseFile[] | null;
  /** How many the account has in total, including any not loaded yet. */
  total: number;
  /** Whether there are older projects still to fetch. */
  hasMore: boolean;
  /** Fetches the next page and appends it. */
  loadMore: () => Promise<void>;
  /** session_id -> title derived from that chat's first user message. */
  titles: Record<string, string>;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  /** Insert or replace one project locally, keeping newest-first order. */
  upsert: (caseFile: CaseFile) => void;
  /** Deletes server-side (case file + transcript + change log), then drops it locally. */
  remove: (sessionId: string) => Promise<void>;
  /** Renames a project - an ordinary Case File edit, logged like any other. */
  rename: (sessionId: string, projectName: string, version?: number) => Promise<CaseFile>;
}

const ProjectsContext = createContext<ProjectsContextValue | null>(null);

function byUpdatedAtDesc(a: CaseFile, b: CaseFile): number {
  return parseApiTimestamp(b.updated_at).getTime() - parseApiTimestamp(a.updated_at).getTime();
}

// One place that owns "the signed-in account's projects", so the chat
// history in the sidebar and the Project History page always agree. Without
// this they'd each fetch their own copy and a delete in one would leave a
// ghost row in the other until a reload.
//
// Signed out this simply holds null: an anonymous case file has no owner
// and therefore isn't listable (see the backend's /users/me/case-files),
// which is Phase 1's behavior and stays that way.
export function ProjectsProvider({ children }: { children: ReactNode }) {
  const { user, loading: authLoading } = useAuth();
  const [projects, setProjects] = useState<CaseFile[] | null>(null);
  const [titles, setTitles] = useState<Record<string, string>>({});
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!user) {
      setProjects(null);
      setTitles({});
      setTotal(0);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // Fetched together: a project list without its titles renders a
      // column of "Untitled project" rows that then shift under the
      // reader a moment later.
      const [page, chatTitles] = await Promise.all([api.myCaseFiles(), api.myChatTitles()]);
      setProjects([...page.items].sort(byUpdatedAtDesc));
      setTotal(page.total);
      setTitles(Object.fromEntries(chatTitles.map((item) => [item.session_id, item.title])));
    } catch (err) {
      setError(err instanceof ApiError ? `Could not load your projects (${err.status}).` : "Could not load your projects.");
    } finally {
      setLoading(false);
    }
  }, [user]);

  // Reload on sign-in, clear on sign-out. Waits for auth to settle so the
  // request carries the Authorization header rather than 401-ing.
  useEffect(() => {
    if (authLoading) return;
    void refresh();
  }, [authLoading, refresh]);

  // Appends the next page rather than replacing, so "load more" keeps
  // what is already on screen.
  const loadMore = useCallback(async () => {
    if (!user) return;
    const offset = projects?.length ?? 0;
    setLoading(true);
    setError(null);
    try {
      const [page, chatTitles] = await Promise.all([
        api.myCaseFiles(PROJECT_PAGE_SIZE, offset),
        api.myChatTitles(PROJECT_PAGE_SIZE, offset),
      ]);
      setProjects((current) => [...(current ?? []), ...page.items].sort(byUpdatedAtDesc));
      setTotal(page.total);
      setTitles((current) => ({
        ...current,
        ...Object.fromEntries(chatTitles.map((item) => [item.session_id, item.title])),
      }));
    } catch (err) {
      setError(err instanceof ApiError ? `Could not load more projects (${err.status}).` : "Could not load more projects.");
    } finally {
      setLoading(false);
    }
  }, [projects, user]);

  const upsert = useCallback((caseFile: CaseFile) => {
    setProjects((current) => {
      // Still signed out, or the list hasn't loaded - nothing to merge into.
      if (current === null) return current;
      const without = current.filter((item) => item.session_id !== caseFile.session_id);
      return [caseFile, ...without].sort(byUpdatedAtDesc);
    });
  }, []);

  const remove = useCallback(async (sessionId: string) => {
    await api.deleteCaseFile(sessionId);
    setProjects((current) => (current === null ? current : current.filter((item) => item.session_id !== sessionId)));
    setTitles((current) => {
      if (!(sessionId in current)) return current;
      const { [sessionId]: _removed, ...rest } = current;
      return rest;
    });
  }, []);

  const rename = useCallback(async (sessionId: string, projectName: string, version?: number) => {
    // The project name IS the Case File's own field, so renaming a chat
    // is an ordinary edit - it shows up in that project's change log like
    // any other, rather than being a separate piece of hidden UI state.
    const updated = await api.updateCaseFile(sessionId, { project_name: projectName }, version);
    setProjects((current) =>
      current === null ? current : current.map((item) => (item.session_id === sessionId ? updated : item)),
    );
    return updated;
  }, []);

  return (
    <ProjectsContext.Provider
      value={{
        projects,
        titles,
        total,
        hasMore: projects !== null && projects.length < total,
        loadMore,
        loading,
        error,
        refresh,
        upsert,
        remove,
        rename,
      }}
    >
      {children}
    </ProjectsContext.Provider>
  );
}

export function useProjects(): ProjectsContextValue {
  const context = useContext(ProjectsContext);
  if (!context) throw new Error("useProjects must be used within a ProjectsProvider");
  return context;
}
