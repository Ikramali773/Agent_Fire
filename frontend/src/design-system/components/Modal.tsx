import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import type { ReactNode, KeyboardEvent } from "react";
import "./Modal.css";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

// Centered dialog for a focused task (e.g. "Upload document"). Keyboard
// accessible: Escape closes, focus is moved into the dialog on open.
export function Modal({ title, onClose, children, footer }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    dialogRef.current?.focus();
  }, []);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") onClose();
  };

  return (
    <div className="ds-modal-overlay" onClick={onClose}>
      <div
        className="ds-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={dialogRef}
        onKeyDown={handleKeyDown}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="ds-modal__header">
          <h2 className="ds-modal__title">{title}</h2>
          <button type="button" className="ds-modal__close" onClick={onClose} aria-label="Close dialog">
            <X aria-hidden="true" />
          </button>
        </header>
        <div className="ds-modal__body">{children}</div>
        {footer && <footer className="ds-modal__footer">{footer}</footer>}
      </div>
    </div>
  );
}
