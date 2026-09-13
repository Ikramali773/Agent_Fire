import { MoreHorizontal, Pencil, Pin, PinOff, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import "./ChatRowMenu.css";

interface Props {
  label: string;
  pinned: boolean;
  onTogglePin: () => void;
  onRename: () => void;
  onDelete: () => void;
}

// Three actions per row is two too many to show inline in a narrow rail,
// so they live behind one overflow button - the same shape Claude and
// ChatGPT use. Closes on Escape and on a click anywhere else, because a
// menu that only closes via its own button strands the reader.
export function ChatRowMenu({ label, pinned, onTogglePin, onRename, onDelete }: Props) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const run = (action: () => void) => () => {
    setOpen(false);
    action();
  };

  return (
    <div className="ds-chat-menu" ref={wrapRef}>
      <button
        type="button"
        className="ds-chat-menu__trigger"
        aria-label={`Actions for ${label}`}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((current) => !current)}
      >
        <MoreHorizontal aria-hidden="true" />
      </button>
      {open && (
        <div className="ds-chat-menu__list" role="menu">
          <button type="button" role="menuitem" className="ds-chat-menu__item" onClick={run(onTogglePin)}>
            {pinned ? <PinOff aria-hidden="true" /> : <Pin aria-hidden="true" />}
            {pinned ? "Unpin" : "Pin"}
          </button>
          <button type="button" role="menuitem" className="ds-chat-menu__item" onClick={run(onRename)}>
            <Pencil aria-hidden="true" />
            Rename
          </button>
          <button
            type="button"
            role="menuitem"
            className="ds-chat-menu__item ds-chat-menu__item--danger"
            onClick={run(onDelete)}
          >
            <Trash2 aria-hidden="true" />
            Delete
          </button>
        </div>
      )}
    </div>
  );
}
