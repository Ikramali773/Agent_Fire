import { useId, useState } from "react";
import type { ReactNode } from "react";
import "./Tooltip.css";

interface Props {
  content: string;
  children: ReactNode;
  side?: "top" | "bottom";
}

// Minimal hover/focus tooltip for short clarifying text (e.g. clause
// reference, disabled-button reason). Not for anything requiring
// interaction - use a Drawer for that.
export function Tooltip({ content, children, side = "top" }: Props) {
  const [visible, setVisible] = useState(false);
  const id = useId();

  return (
    <span
      className="ds-tooltip"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      <span aria-describedby={visible ? id : undefined}>{children}</span>
      {visible && (
        <span role="tooltip" id={id} className={`ds-tooltip__bubble ds-tooltip__bubble--${side}`}>
          {content}
        </span>
      )}
    </span>
  );
}
