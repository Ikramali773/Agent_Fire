import { useState } from "react";
import type { ReactNode } from "react";
import { CaseInspector } from "./CaseInspector";
import { DisclaimerFooter } from "./DisclaimerFooter";
import { Sidebar } from "./Sidebar";
import { TopHeader, type SyncState } from "./TopHeader";
import { NAV_ITEMS, type ViewKey } from "./nav";
import type { CaseFile } from "../types";
import "./Shell.css";

interface Props {
  activeView: ViewKey;
  onNavigate: (view: ViewKey) => void;
  projectName: string;
  location: string;
  codeEdition: "2026" | "2016";
  syncState: SyncState;
  caseFile: CaseFile | null;
  onOpenChat: (caseFile: CaseFile) => void;
  onNewChat: () => void;
  onChatDeleted: (sessionId: string) => void;
  children: ReactNode;
}

// The one shell frame every page renders inside - header, left nav, center
// workspace, right case inspector, disclaimer footer. Only the center
// content swaps between views; this frame is built to carry unchanged
// through Phases 2-5 (the plan workspace in Phase 4 reuses these same
// regions rather than requiring a rebuild).
function isNarrowViewport(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(max-width: 1200px)").matches;
}

export function Shell({
  activeView,
  onNavigate,
  projectName,
  location,
  codeEdition,
  syncState,
  caseFile,
  onOpenChat,
  onNewChat,
  onChatDeleted,
  children,
}: Props) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  // Below 1200px the inspector renders as a bottom sheet over the page
  // content (see CaseInspector.css), so it starts collapsed there - open by
  // default would permanently hide the composer/page beneath it.
  const [inspectorCollapsed, setInspectorCollapsed] = useState(isNarrowViewport);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const activeLabel = NAV_ITEMS.find((item) => item.key === activeView)?.label ?? "";

  return (
    <div className="ds-shell">
      <TopHeader
        projectName={projectName}
        location={location}
        breadcrumb={["Projects", projectName, activeLabel]}
        codeEdition={codeEdition}
        syncState={syncState}
        onMenuClick={() => setMobileNavOpen((open) => !open)}
      />
      <div className="ds-shell__body">
        {mobileNavOpen && <div className="ds-shell__mobile-backdrop" onClick={() => setMobileNavOpen(false)} />}
        <div className={`ds-shell__sidebar-wrap${mobileNavOpen ? " ds-shell__sidebar-wrap--open" : ""}`}>
          <Sidebar
            activeView={activeView}
            onNavigate={(view) => {
              onNavigate(view);
              setMobileNavOpen(false);
            }}
            collapsed={sidebarCollapsed}
            onToggleCollapsed={() => setSidebarCollapsed((c) => !c)}
            activeSessionId={caseFile?.session_id ?? null}
            onOpenChat={(opened) => {
              onOpenChat(opened);
              setMobileNavOpen(false);
            }}
            onNewChat={() => {
              onNewChat();
              setMobileNavOpen(false);
            }}
            onChatDeleted={onChatDeleted}
          />
        </div>
        <main className="ds-shell__main">{children}</main>
        {!inspectorCollapsed && <div className="ds-shell__mobile-backdrop ds-shell__mobile-backdrop--inspector" onClick={() => setInspectorCollapsed(true)} />}
        <CaseInspector caseFile={caseFile} collapsed={inspectorCollapsed} onToggleCollapsed={() => setInspectorCollapsed((c) => !c)} />
      </div>
      <DisclaimerFooter />
    </div>
  );
}
