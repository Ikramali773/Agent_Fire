import { Pencil } from "lucide-react";
import { useState } from "react";
import type { KeyboardEvent } from "react";
import { SourceBadge, type FieldSourceKind } from "./SourceBadge";
import "./DataRow.css";

interface Props {
  label: string;
  value: React.ReactNode;
  source?: FieldSourceKind;
  confidence?: number | null;
  /** Present only when this field is actually editable (wired to a real save). */
  onSave?: (nextValue: string) => void;
  editValue?: string;
  compact?: boolean;
}

// The single row primitive for every "fact about the building" surface in
// the product - the Case Inspector panel (compact) and the full Case File
// page (same component, just not passed `compact`). Never a giant card per
// field - see the design brief's "compact rows, not cards" requirement.
export function DataRow({ label, value, source, confidence, onSave, editValue, compact }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(editValue ?? "");

  const commit = () => {
    setEditing(false);
    if (onSave && draft !== editValue) onSave(draft);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") commit();
    if (event.key === "Escape") {
      setDraft(editValue ?? "");
      setEditing(false);
    }
  };

  return (
    <div className={`ds-data-row${compact ? " ds-data-row--compact" : ""}`}>
      <span className="ds-data-row__label">{label}</span>
      {editing ? (
        <input
          className="ds-data-row__input"
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={handleKeyDown}
          aria-label={`Edit ${label}`}
        />
      ) : (
        <span className="ds-data-row__value tabular-nums">{value}</span>
      )}
      <span className="ds-data-row__meta">
        {source && <SourceBadge source={source} confidence={confidence} />}
        {onSave && !editing && (
          <button
            type="button"
            className="ds-data-row__edit"
            onClick={() => {
              setDraft(editValue ?? "");
              setEditing(true);
            }}
            aria-label={`Edit ${label}`}
          >
            <Pencil aria-hidden="true" />
          </button>
        )}
      </span>
    </div>
  );
}
