import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import type { ReactNode, KeyboardEvent } from "react";
import "./Drawer.css";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

// Right-side sheet for drilling into one item without leaving the page
// (a compliance finding, a plan annotation, a review item). On narrow
// viewports this same component renders as a bottom sheet - see Drawer.css.
export function Drawer({ title, onClose, children, footer }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panelRef.current?.focus();
  }, []);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") onClose();
  };

  return (
    <div className="ds-drawer-overlay" onClick={onClose}>
      <div
        className="ds-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={panelRef}
        onKeyDown={handleKeyDown}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="ds-drawer__header">
          <h2 className="ds-drawer__title">{title}</h2>
          <button type="button" className="ds-drawer__close" onClick={onClose} aria-label="Close panel">
            <X aria-hidden="true" />
          </button>
        </header>
        <div className="ds-drawer__body">{children}</div>
        {footer && <footer className="ds-drawer__footer">{footer}</footer>}
      </div>
    </div>
  );
}
