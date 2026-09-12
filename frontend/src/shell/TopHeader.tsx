import { Bell, ChevronRight, CircleCheck, HelpCircle, Loader2, Menu } from "lucide-react";
import { Badge } from "../design-system/components/Badge";
import "./TopHeader.css";

export type SyncState = "saved" | "saving";

interface Props {
  projectName: string;
  location: string;
  breadcrumb: string[];
  codeEdition: "2026" | "2016";
  syncState: SyncState;
  onMenuClick: () => void;
  userLabel: string;
}

export function TopHeader({ projectName, location, breadcrumb, codeEdition, syncState, onMenuClick, userLabel }: Props) {
  const initial = userLabel.trim().charAt(0).toUpperCase() || "?";

  return (
    <header className="ds-top-header">
      <div className="ds-top-header__section ds-top-header__section--left">
        <button type="button" className="ds-top-header__menu-btn" onClick={onMenuClick} aria-label="Toggle navigation">
          <Menu aria-hidden="true" />
        </button>
        <div className="ds-top-header__project">
          <span className="ds-top-header__project-name">{projectName}</span>
          <span className="ds-top-header__project-location">{location}</span>
        </div>
      </div>

      <nav className="ds-top-header__breadcrumb" aria-label="Breadcrumb">
        {breadcrumb.map((crumb, index) => (
          <span key={crumb} className="ds-top-header__crumb-group">
            {index > 0 && <ChevronRight className="ds-top-header__crumb-sep" aria-hidden="true" />}
            <span className={index === breadcrumb.length - 1 ? "ds-top-header__crumb ds-top-header__crumb--current" : "ds-top-header__crumb"}>
              {crumb}
            </span>
          </span>
        ))}
      </nav>

      <div className="ds-top-header__section ds-top-header__section--right">
        <span title={codeEdition === "2026" ? "NBCS 2026 — primary code edition" : "NBC 2016 — legacy code edition"}>
          <Badge tone="accent">{codeEdition === "2026" ? "NBCS 2026 · Primary" : "NBC 2016 · Legacy"}</Badge>
        </span>

        <span className="ds-top-header__sync" aria-live="polite">
          {syncState === "saving" ? (
            <>
              <Loader2 className="ds-top-header__sync-icon ds-top-header__sync-icon--spin" aria-hidden="true" />
              Saving…
            </>
          ) : (
            <>
              <CircleCheck className="ds-top-header__sync-icon" aria-hidden="true" />
              Saved
            </>
          )}
        </span>

        <button type="button" className="ds-top-header__icon-btn" aria-label="Help">
          <HelpCircle aria-hidden="true" />
        </button>
        <button type="button" className="ds-top-header__icon-btn" aria-label="Notifications">
          <Bell aria-hidden="true" />
        </button>
        <span className="ds-top-header__avatar" title={userLabel} aria-label={userLabel}>
          {initial}
        </span>
      </div>
    </header>
  );
}
