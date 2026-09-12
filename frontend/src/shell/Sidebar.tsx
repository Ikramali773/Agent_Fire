import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Badge } from "../design-system/components/Badge";
import { NAV_ITEMS, type ViewKey } from "./nav";
import "./Sidebar.css";

interface Props {
  activeView: ViewKey;
  onNavigate: (view: ViewKey) => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

export function Sidebar({ activeView, onNavigate, collapsed, onToggleCollapsed }: Props) {
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
