import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { LoginModal } from "../../auth/LoginModal";
import { Button } from "../../design-system/components/Button";
import { EmptyState } from "../../design-system/components/EmptyState";
import { StatusPill } from "../../design-system/components/StatusPill";
import { formatLabel, normalizeClassification } from "../../lib/caseFileFields";
import { parseApiTimestamp } from "../../lib/relativeTime";
import { DeleteProjectDialog } from "../../projects/DeleteProjectDialog";
import { useProjects } from "../../projects/ProjectsContext";
import { overallStatus } from "../compliance/complianceStatus";
import type { CaseFile } from "../../types";
import "./ProjectHistoryPage.css";

interface Props {
  activeSessionId: string | null;
  onOpenCaseFile: (caseFile: CaseFile) => void;
  onStartNewProject: () => void;
  onProjectDeleted: (sessionId: string) => void;
}

// Phase 2's starting point for Project History: every case file the signed-
// in account owns, so a project can be found again later instead of only
// ever existing in the tab that created it. This is a project LIST, not a
// field-level change log - GET /users/me/case-files returns each case
// file's current state only; a true "what changed and when" audit trail
// (per-field diffs over time) isn't built yet.
//
// The list itself comes from ProjectsContext, shared with the sidebar's
// chat rail, so deleting in one place updates the other immediately.
export function ProjectHistoryPage({ activeSessionId, onOpenCaseFile, onStartNewProject, onProjectDeleted }: Props) {
  const { user } = useAuth();
  const { projects, total, hasMore, loadMore, loading, error } = useProjects();
  const [loginOpen, setLoginOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<CaseFile | null>(null);

  if (!user) {
    return (
      <div className="ds-project-history">
        <EmptyState
          title="Sign in to see your projects"
          description="Project History lists every case file your account owns, so you can find one again later. Sign in or create an account to start building history."
          action={
            <Button variant="primary" size="sm" onClick={() => setLoginOpen(true)}>
              Sign in
            </Button>
          }
        />
        {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
      </div>
    );
  }

  return (
    <div className="ds-project-history">
      <header className="ds-project-history__header">
        <div>
          <h1>Project History</h1>
          <p>Every case file your account owns. Case files created before you signed in aren't included.</p>
        </div>
        {/* A project is only created once you actually start one, so this is
            how you deliberately begin a second one rather than continuing
            the active project on the Overview page. */}
        <Button variant="secondary" size="sm" icon={<Plus />} onClick={onStartNewProject}>
          New project
        </Button>
      </header>

      {error && (
        <div className="ds-project-history__error" role="alert">
          {error}
        </div>
      )}

      {projects === null && loading && !error && <p className="ds-project-history__loading">Loading…</p>}

      {projects !== null && projects.length === 0 && (
        <EmptyState
          title="No projects yet"
          description="Start a conversation on the Overview page while signed in, and it'll show up here."
        />
      )}

      {projects !== null && projects.length > 0 && (
        <table className="ds-project-history__table">
          <thead>
            <tr>
              <th>Project</th>
              <th>Location</th>
              <th>Stage</th>
              <th>Status</th>
              <th>Last updated</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {projects.map((caseFile) => {
              const result = normalizeClassification(caseFile.classification_result);
              const isClassified = caseFile.conversation_stage === "classified" && Boolean(result.table_7_ref);
              return (
                <tr key={caseFile.session_id} className={caseFile.session_id === activeSessionId ? "ds-project-history__row--active" : undefined}>
                  <td>{caseFile.project_name || "Untitled project"}</td>
                  <td>{[caseFile.city, caseFile.state].filter(Boolean).join(", ") || "Not yet known"}</td>
                  <td>{formatLabel(caseFile.project_stage)}</td>
                  <td>{isClassified ? <StatusPill status={overallStatus(result)} size="sm" /> : <StatusPill status="unknown" label="Not classified" size="sm" />}</td>
                  <td className="tabular-nums">{parseApiTimestamp(caseFile.updated_at).toLocaleString()}</td>
                  <td>
                    <div className="ds-project-history__actions">
                      {/* Opens the conversation, not the field view - picking
                          a project up again almost always means continuing
                          the chat, and Case File is one nav click away. */}
                      <Button variant="secondary" size="sm" onClick={() => onOpenCaseFile(caseFile)}>
                        Open chat
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<Trash2 />}
                        iconOnly
                        aria-label={`Delete ${caseFile.project_name || "Untitled project"}`}
                        title="Delete project"
                        onClick={() => setPendingDelete(caseFile)}
                      />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {hasMore && (
        <div className="ds-project-history__more">
          <Button variant="secondary" size="sm" onClick={() => void loadMore()} disabled={loading}>
            {loading ? "Loading…" : `Show more (${(projects?.length ?? 0)} of ${total})`}
          </Button>
        </div>
      )}

      {pendingDelete && (
        <DeleteProjectDialog project={pendingDelete} onClose={() => setPendingDelete(null)} onDeleted={onProjectDeleted} />
      )}
    </div>
  );
}
