import type { ReactNode } from "react";
import "./Card.css";

interface Props {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}

// A low-emphasis section container - 1px border, minimal radius, no heavy
// shadow. Used for grouping (Case File sections, Compliance requirement
// groups), never as a decorative "card" per data point.
export function Card({ title, actions, children, className, padded = true }: Props) {
  return (
    <section className={["ds-card", className].filter(Boolean).join(" ")}>
      {(title || actions) && (
        <header className="ds-card__header">
          {title && <h3 className="ds-card__title">{title}</h3>}
          {actions && <div className="ds-card__actions">{actions}</div>}
        </header>
      )}
      <div className={padded ? "ds-card__body" : undefined}>{children}</div>
    </section>
  );
}
