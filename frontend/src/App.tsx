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
import { ReviewPage } from "./pages/review/ReviewPage";
import { useProjects } from "./projects/ProjectsContext";
import { NAV_ITEMS, type ViewKey } from "./shell/nav";
import { Shell } from "./shell/Shell";
import type { CaseFile } from "./types";

// Which project this browser was last working on. Only the id is stored -
// the case file itself is always re-fetched from the server, never trusted
// from local storage.
const ACTIVE_SESSION_KEY = "fire-agent-active-session";

function App() {
  const { user, loading: authLoading } = useAuth();
  const { upsert: upsertProject, refresh: refreshProjects } = useProjects();
  const [activeView, setActiveView] = useState<ViewKey>("overview");
  const [caseFileState, setCaseFileState] = useState<CaseFile | null>(null);
  const [busy, setBusy] = useState(false);
  const [restoring, setRestoring] = useState(true);

  const setCaseFile = useCallback(
    (next: CaseFile | null) => {
      setCaseFileState(next);
      // Keep the chat rail in step with the live project: this is what
      // makes a brand-new conversation appear there the moment it is
      // created, and its title update once the project is named.
      if (next) upsertProject(next);
      try {
        if (next) localStorage.setItem(ACTIVE_SESSION_KEY, next.session_id);
        else localStorage.removeItem(ACTIVE_SESSION_KEY);
      } catch {
        // Private browsing / storage disabled - losing the "resume where I
        // left off" convenience is fine, breaking the app over it is not.
      }
    },
    [upsertProject],
  );

  // Opening a chat means continuing the conversation, so it always lands on
  // Overview - the Case File view shows the extracted fields, not the chat.
  const openChat = useCallback(
    (opened: CaseFile) => {
      setCaseFile(opened);
      setActiveView("overview");
    },
    [setCaseFile],
  );

  // Clearing the active case file is all it takes: the Overview page
  // creates one lazily on the first real input, so this starts a blank
  // conversation without persisting anything yet.
  const startNewChat = useCallback(() => {
    setCaseFile(null);
    setActiveView("overview");
  }, [setCaseFile]);

  // A rename is an ordinary Case File edit, so the open project has to
  // pick it up too - otherwise the header would keep showing the old name
  // until the next navigation.
  const handleProjectRenamed = useCallback((renamed: CaseFile) => {
    setCaseFileState((current) => (current?.session_id === renamed.session_id ? renamed : current));
  }, []);

  const handleProjectDeleted = useCallback(
    (sessionId: string) => {
      // Only the project that was actually deleted gets dropped - deleting
      // some other chat must not disturb what the user is working on.
      setCaseFileState((current) => {
        if (current?.session_id !== sessionId) return current;
        try {
          localStorage.removeItem(ACTIVE_SESSION_KEY);
        } catch {
          /* ignore */
        }
        return null;
      });
    },
    [],
  );

  // Claim the open project when someone signs in mid-conversation.
  // `owner_user_id` is otherwise only set at creation, so a project started
  // while signed out stayed anonymous forever - invisible in Project
  // History and the chat rail, even to the person who just created it.
  // Claiming is idempotent server-side, so StrictMode's double-invoke and
  // any retry are harmless.
  useEffect(() => {
    if (!user || !caseFileState || caseFileState.owner_user_id !== null) return;
    const sessionId = caseFileState.session_id;
    void api
      .claimCaseFile(sessionId)
      .then((claimed) => {
        setCaseFileState((current) => (current?.session_id === sessionId ? claimed : current));
        // The projects list was fetched at sign-in, before this case file
        // had an owner, so it would not include it yet.
        return refreshProjects();
      })
      .catch(() => {
        // Already someone else's, or gone - either way there is nothing
        // for the user to do about it, and the conversation still works.
      });
  }, [user, caseFileState, refreshProjects]);

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
      onOpenChat={openChat}
      onNewChat={startNewChat}
      onChatDeleted={handleProjectDeleted}
      onChatRenamed={handleProjectRenamed}
    >
      {/* Nothing renders until the "resume last project" lookup settles -
          otherwise Overview would briefly open a blank draft conversation
          for a project that's about to load a moment later. */}
      {restoring && <div className="ds-app-restoring">Loading your workspace…</div>}
      {!restoring && activeView === "overview" && (
        <OverviewPage caseFile={caseFile} onCaseFileChange={setCaseFile} onBusyChange={setBusy} />
      )}
      {!restoring && activeView === "case-file" && <CaseFilePage caseFile={caseFile} onCaseFileChange={setCaseFile} onGoToReview={() => setActiveView("review")} />}
      {!restoring && activeView === "documents" && <DocumentsPage caseFile={caseFile} onCaseFileChange={setCaseFile} />}
      {!restoring && activeView === "compliance" && <CompliancePage caseFile={caseFile} onGoToReview={() => setActiveView("review")} />}
      {!restoring && activeView === "reports" && <ReportsPage caseFile={caseFile} />}
      {!restoring && activeView === "review" && <ReviewPage caseFile={caseFile} onCaseFileChange={setCaseFile} />}
      {!restoring && activeView === "history" && (
        <ProjectHistoryPage
          activeSessionId={caseFile?.session_id ?? null}
          onOpenCaseFile={openChat}
          onStartNewProject={startNewChat}
          onProjectDeleted={handleProjectDeleted}
        />
      )}
      {!restoring && (activeView === "plans" || activeView === "findings") &&
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
    default:
      return "This part of the workspace isn't active yet.";
  }
}

export default App;
