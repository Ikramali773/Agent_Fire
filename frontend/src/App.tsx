import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import { useAuth } from "./auth/AuthContext";
import { CompliancePage } from "./pages/compliance/CompliancePage";
import { CaseFilePage } from "./pages/case-file/CaseFilePage";
import { ComingSoonPage } from "./pages/ComingSoonPage";
import { DocumentsPage } from "./pages/documents/DocumentsPage";
import { ProjectHistoryPage } from "./pages/history/ProjectHistoryPage";
import { OverviewPage } from "./pages/overview/OverviewPage";
import { ReportsPage } from "./pages/reports/ReportsPage";
import { NAV_ITEMS, type ViewKey } from "./shell/nav";
import { Shell } from "./shell/Shell";
import type { CaseFile } from "./types";

// Which project this browser was last working on. Only the id is stored -
// the case file itself is always re-fetched from the server, never trusted
// from local storage.
const ACTIVE_SESSION_KEY = "fire-agent-active-session";

function App() {
  const { loading: authLoading } = useAuth();
  const [activeView, setActiveView] = useState<ViewKey>("overview");
  const [caseFileState, setCaseFileState] = useState<CaseFile | null>(null);
  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState(true);

  const setCaseFile = useCallback((next: CaseFile | null) => {
    setCaseFileState(next);
    try {
      if (next) localStorage.setItem(ACTIVE_SESSION_KEY, next.session_id);
      else localStorage.removeItem(ACTIVE_SESSION_KEY);
    } catch {
      // Private browsing / storage disabled - losing the "resume where I
      // left off" convenience is fine, breaking the app over it is not.
    }
  }, []);

  // Reopen the last project on reload, so a refresh doesn't strand the user
  // in a blank conversation with their history only reachable via Project
  // History. Waits for auth to settle first: an owned case file needs the
  // Authorization header, and fetching before it's applied would 403 and
  // look like the project had vanished.
  useEffect(() => {
    if (authLoading) return;
    let stored: string | null = null;
    try {
      stored = localStorage.getItem(ACTIVE_SESSION_KEY);
    } catch {
      stored = null;
    }
    if (!stored) {
      setRestoring(false);
      return;
    }
    api
      .getCaseFile(stored)
      .then(setCaseFileState)
      .catch(() => {
        // Deleted, or belongs to a different account now - forget it and
        // start fresh rather than showing an error the user can't act on.
        try {
          localStorage.removeItem(ACTIVE_SESSION_KEY);
        } catch {
          /* ignore */
        }
      })
      .finally(() => setRestoring(false));
  }, [authLoading]);

  const caseFile = caseFileState;

  return (
    <Shell
      activeView={activeView}
      onNavigate={setActiveView}
      projectName={caseFile?.project_name || "Untitled project"}
      location={[caseFile?.city, caseFile?.state].filter(Boolean).join(", ") || "Location not yet known"}
      codeEdition={caseFile?.code_edition ?? "2026"}
      syncState={busy ? "saving" : "saved"}
      caseFile={caseFile}
    >
      {/* Nothing renders until the "resume last project" lookup settles -
          otherwise Overview would briefly open a blank draft conversation
          for a project that's about to load a moment later. */}
      {restoring && <div className="ds-app-restoring">Loading your workspace…</div>}
      {!restoring && activeView === "overview" && (
        <OverviewPage caseFile={caseFile} onCaseFileChange={setCaseFile} onBusyChange={setBusy} />
      )}
      {!restoring && activeView === "case-file" && <CaseFilePage caseFile={caseFile} onCaseFileChange={setCaseFile} />}
      {!restoring && activeView === "documents" && <DocumentsPage caseFile={caseFile} onCaseFileChange={setCaseFile} />}
      {!restoring && activeView === "compliance" && <CompliancePage caseFile={caseFile} />}
      {!restoring && activeView === "reports" && <ReportsPage caseFile={caseFile} />}
      {!restoring && activeView === "history" && (
        <ProjectHistoryPage
          onOpenCaseFile={(opened) => {
            setCaseFile(opened);
            setActiveView("case-file");
          }}
          onStartNewProject={() => {
            // Clearing the active case file is all it takes: the Overview
            // page creates one lazily on the first real input, so this
            // starts a blank conversation without persisting anything yet.
            setCaseFile(null);
            setActiveView("overview");
          }}
        />
      )}
      {!restoring && (activeView === "plans" || activeView === "findings" || activeView === "review") &&
        (() => {
          const item = NAV_ITEMS.find((nav) => nav.key === activeView)!;
          return (
            <ComingSoonPage
              icon={item.icon}
              title={item.label}
              phase={item.comingInPhase ?? 2}
              description={comingSoonDescription(activeView)}
            />
          );
        })()}
    </Shell>
  );
}

function comingSoonDescription(view: ViewKey): string {
  switch (view) {
    case "plans":
      return "Geometry-aware plan viewing arrives once the Building Digital Model is built.";
    case "findings":
      return "Compliance findings will be shown here alongside the plan they were derived from.";
    case "review":
      return "A structured review queue for handing off human-review cases to a licensed consultant.";
    default:
      return "This part of the workspace isn't active yet.";
  }
}

export default App;
