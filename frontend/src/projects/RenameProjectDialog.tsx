import { useState } from "react";
import { ApiError } from "../api/client";
import { Button } from "../design-system/components/Button";
import { Modal } from "../design-system/components/Modal";
import { projectLabel } from "../lib/caseFileFields";
import { useProjects } from "./ProjectsContext";
import type { CaseFile } from "../types";
import "./RenameProjectDialog.css";

interface Props {
  project: CaseFile;
  /** The derived chat title, used as the placeholder when unnamed. */
  chatTitle?: string;
  onClose: () => void;
  onRenamed: (caseFile: CaseFile) => void;
}

// Renaming sets the Case File's own project_name, so it is an ordinary
// edit: it appears in that project's change log like any other, rather
// than being separate hidden UI state.
export function RenameProjectDialog({ project, chatTitle, onClose, onRenamed }: Props) {
  const { rename } = useProjects();
  const [name, setName] = useState(project.project_name ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      onRenamed(await rename(project.session_id, name.trim()));
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? `Could not rename this project (${err.status}).` : "Could not rename this project.");
      setSaving(false);
    }
  };

  return (
    <Modal
      title="Rename project"
      onClose={saving ? () => undefined : onClose}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" onClick={(event) => void handleSubmit(event)} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <form className="ds-rename-project" onSubmit={(event) => void handleSubmit(event)}>
        <label className="ds-rename-project__label" htmlFor="ds-rename-project-input">
          Project name
        </label>
        <input
          id="ds-rename-project-input"
          className="ds-rename-project__input"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={projectLabel(project, chatTitle)}
          autoFocus
          disabled={saving}
        />
        <p className="ds-rename-project__hint">
          This is the Case File's project name, so it also updates the report and Project History. Clear it to fall back to the
          conversation's own title.
        </p>
        {/* A submit button the dialog's footer already provides - present
            so pressing Enter in the field submits rather than doing
            nothing. */}
        <button type="submit" hidden aria-hidden="true" tabIndex={-1} />
      </form>
      {error && (
        <p className="ds-rename-project__error" role="alert">
          {error}
        </p>
      )}
    </Modal>
  );
}
