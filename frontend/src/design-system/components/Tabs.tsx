import "./Tabs.css";

export interface TabItem {
  key: string;
  label: string;
  disabled?: boolean;
  badge?: React.ReactNode;
}

interface Props {
  tabs: TabItem[];
  active: string;
  onChange: (key: string) => void;
}

// Section-level navigation within a page (e.g. Compliance: Requirements /
// Findings / History). Not for top-level app navigation - that's Sidebar.
export function Tabs({ tabs, active, onChange }: Props) {
  return (
    <div className="ds-tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={tab.key === active}
          disabled={tab.disabled}
          className={`ds-tabs__tab${tab.key === active ? " ds-tabs__tab--active" : ""}`}
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
          {tab.badge && <span className="ds-tabs__badge">{tab.badge}</span>}
        </button>
      ))}
    </div>
  );
}
