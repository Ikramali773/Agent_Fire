import { useState } from "react";
import { ApiError } from "../api/client";
import { Button } from "../design-system/components/Button";
import { Modal } from "../design-system/components/Modal";
import { projectLabel } from "../lib/caseFileFields";
import { useProjects } from "./ProjectsContext";
import type { CaseFile } from "../types";
import "./DeleteProjectDialog.css";

interface Props {
  project: CaseFile;
  onClose: () => void;
  /** Called after the project is actually gone from the server. */
  onDeleted: (sessionId: string) => void;
}

// Deleting is irreversible and takes the conversation with it, so it is
// confirmed in a real dialog - not window.confirm, which can't say what
// else goes with it and can't show the failure if the request is rejected.
export function DeleteProjectDialog({ project, onClose, onDeleted }: Props) {
  const { remove } = useProjects();
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDelete = async () => {
    setDeleting(true);
    setError(null);
    try {
      await remove(project.session_id);
      onDeleted(project.session_id);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? `Could not delete this project (${err.status}).` : "Could not delete this project.");
      setDeleting(false);
    }
  };

  return (
    <Modal
      title="Delete this project?"
      onClose={deleting ? () => undefined : onClose}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={deleting}>
            Cancel
          </Button>
          <Button variant="danger" size="sm" onClick={handleDelete} disabled={deleting}>
            {deleting ? "Deleting…" : "Delete project"}
          </Button>
        </>
      }
    >
      <p className="ds-delete-project__name">{projectLabel(project)}</p>
      <p className="ds-delete-project__body">
        This permanently deletes the case file and its entire chat history. Any report generated from it will no longer be
        available. This cannot be undone.
      </p>
      {error && (
        <p className="ds-delete-project__error" role="alert">
          {error}
        </p>
      )}
    </Modal>
  );
}
