import { useState } from "react";
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

function App() {
  const [activeView, setActiveView] = useState<ViewKey>("overview");
  const [caseFile, setCaseFile] = useState<CaseFile | null>(null);
  const [busy, setBusy] = useState(false);

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
      {activeView === "overview" && <OverviewPage caseFile={caseFile} onCaseFileChange={setCaseFile} onBusyChange={setBusy} />}
      {activeView === "case-file" && <CaseFilePage caseFile={caseFile} onCaseFileChange={setCaseFile} />}
      {activeView === "documents" && <DocumentsPage caseFile={caseFile} onCaseFileChange={setCaseFile} />}
      {activeView === "compliance" && <CompliancePage caseFile={caseFile} />}
      {activeView === "reports" && <ReportsPage caseFile={caseFile} />}
      {activeView === "history" && (
        <ProjectHistoryPage
          onOpenCaseFile={(opened) => {
            setCaseFile(opened);
            setActiveView("case-file");
          }}
        />
      )}
      {(activeView === "plans" || activeView === "findings" || activeView === "review") &&
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
