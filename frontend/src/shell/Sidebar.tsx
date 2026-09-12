import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Badge } from "../design-system/components/Badge";
import { RecentChats } from "./RecentChats";
import { NAV_ITEMS, type ViewKey } from "./nav";
import type { CaseFile } from "../types";
import "./Sidebar.css";

interface Props {
  activeView: ViewKey;
  onNavigate: (view: ViewKey) => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  activeSessionId: string | null;
  onOpenChat: (caseFile: CaseFile) => void;
  onNewChat: () => void;
  onChatDeleted: (sessionId: string) => void;
}

export function Sidebar({
  activeView,
  onNavigate,
  collapsed,
  onToggleCollapsed,
  activeSessionId,
  onOpenChat,
  onNewChat,
  onChatDeleted,
}: Props) {
  return (
    <nav className={`ds-sidebar${collapsed ? " ds-sidebar--collapsed" : ""}`} aria-label="Primary">
      <ul className="ds-sidebar__list">
        {NAV_ITEMS.map((item) => {
          const disabled = Boolean(item.comingInPhase);
          const Icon = item.icon;
          return (
            <li key={item.key}>
              <button
                type="button"
                className={`ds-sidebar__item${item.key === activeView ? " ds-sidebar__item--active" : ""}`}
                onClick={() => !disabled && onNavigate(item.key)}
                aria-disabled={disabled}
                aria-current={item.key === activeView ? "page" : undefined}
                title={disabled ? `${item.label} — coming in Phase ${item.comingInPhase}` : item.label}
              >
                <Icon className="ds-sidebar__icon" aria-hidden="true" />
                {!collapsed && <span className="ds-sidebar__label">{item.label}</span>}
                {!collapsed && disabled && (
                  <span className="ds-sidebar__phase-badge">
                    <Badge tone="phase">Phase {item.comingInPhase}</Badge>
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
      {/* Collapsed to an icon rail there is no room for chat titles, so the
          section is dropped entirely rather than shown truncated to nothing. */}
      {!collapsed && (
        <RecentChats
          activeSessionId={activeSessionId}
          onOpenChat={onOpenChat}
          onNewChat={onNewChat}
          onViewAll={() => onNavigate("history")}
          onDeleted={onChatDeleted}
        />
      )}
      <button
        type="button"
        className="ds-sidebar__collapse-toggle"
        onClick={onToggleCollapsed}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <PanelLeftOpen aria-hidden="true" /> : <PanelLeftClose aria-hidden="true" />}
        {!collapsed && <span>Collapse</span>}
      </button>
    </nav>
  );
}
