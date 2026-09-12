import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type { CaseFile } from "../types";

interface ProjectsContextValue {
  /** null until the first load finishes (or while signed out). */
  projects: CaseFile[] | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  /** Insert or replace one project locally, keeping newest-first order. */
  upsert: (caseFile: CaseFile) => void;
  /** Deletes server-side (case file + transcript), then drops it locally. */
  remove: (sessionId: string) => Promise<void>;
}

const ProjectsContext = createContext<ProjectsContextValue | null>(null);

function byUpdatedAtDesc(a: CaseFile, b: CaseFile): number {
  return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!user) {
      setProjects(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const list = await api.myCaseFiles();
      setProjects([...list].sort(byUpdatedAtDesc));
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
  }, []);

  return (
    <ProjectsContext.Provider value={{ projects, loading, error, refresh, upsert, remove }}>
      {children}
    </ProjectsContext.Provider>
  );
}

export function useProjects(): ProjectsContextValue {
  const context = useContext(ProjectsContext);
  if (!context) throw new Error("useProjects must be used within a ProjectsProvider");
  return context;
}
