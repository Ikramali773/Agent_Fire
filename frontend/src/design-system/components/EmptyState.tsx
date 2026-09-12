import type { ReactNode } from "react";
import "./EmptyState.css";

interface Props {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

// Intentional empty state - what this section will contain and the one
// action that fills it. Never a bare "No data" string.
export function EmptyState({ icon, title, description, action }: Props) {
  return (
    <div className="ds-empty-state">
      {icon && <div className="ds-empty-state__icon">{icon}</div>}
      <p className="ds-empty-state__title">{title}</p>
      {description && <p className="ds-empty-state__description">{description}</p>}
      {action && <div className="ds-empty-state__action">{action}</div>}
    </div>
  );
}
