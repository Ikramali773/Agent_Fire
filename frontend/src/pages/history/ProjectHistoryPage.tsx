import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { LoginModal } from "../../auth/LoginModal";
import { Button } from "../../design-system/components/Button";
import { EmptyState } from "../../design-system/components/EmptyState";
import { StatusPill } from "../../design-system/components/StatusPill";
import { formatLabel, normalizeClassification } from "../../lib/caseFileFields";
import { overallStatus } from "../compliance/complianceStatus";
import type { CaseFile } from "../../types";
import "./ProjectHistoryPage.css";

interface Props {
  onOpenCaseFile: (caseFile: CaseFile) => void;
  onStartNewProject: () => void;
}

// Phase 2's starting point for Project History: every case file the signed-
// in account owns, so a project can be found again later instead of only
// ever existing in the tab that created it. This is a project LIST, not a
// field-level change log - GET /users/me/case-files returns each case
// file's current state only; a true "what changed and when" audit trail
// (per-field diffs over time) isn't built yet.
export function ProjectHistoryPage({ onOpenCaseFile, onStartNewProject }: Props) {
  const { user } = useAuth();
  const [caseFiles, setCaseFiles] = useState<CaseFile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);

  useEffect(() => {
    if (!user) return;
    setError(null);
    api
      .myCaseFiles()
      .then(setCaseFiles)
      .catch((err) => setError(err instanceof ApiError ? `Could not load your projects (${err.status}).` : "Could not load your projects."));
  }, [user]);

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

      {caseFiles === null && !error && <p className="ds-project-history__loading">Loading…</p>}

      {caseFiles !== null && caseFiles.length === 0 && (
        <EmptyState
          title="No projects yet"
          description="Start a conversation on the Overview page while signed in, and it'll show up here."
        />
      )}

      {caseFiles !== null && caseFiles.length > 0 && (
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
            {caseFiles.map((caseFile) => {
              const result = normalizeClassification(caseFile.classification_result);
              const isClassified = caseFile.conversation_stage === "classified" && Boolean(result.table_7_ref);
              return (
                <tr key={caseFile.session_id}>
                  <td>{caseFile.project_name || "Untitled project"}</td>
                  <td>{[caseFile.city, caseFile.state].filter(Boolean).join(", ") || "Not yet known"}</td>
                  <td>{formatLabel(caseFile.project_stage)}</td>
                  <td>{isClassified ? <StatusPill status={overallStatus(result)} size="sm" /> : <StatusPill status="unknown" label="Not classified" size="sm" />}</td>
                  <td className="tabular-nums">{new Date(caseFile.updated_at).toLocaleString()}</td>
                  <td>
                    <Button variant="secondary" size="sm" onClick={() => onOpenCaseFile(caseFile)}>
                      Open
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
