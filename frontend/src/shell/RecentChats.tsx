import { MessageSquare, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { LoginModal } from "../auth/LoginModal";
import { DeleteProjectDialog } from "../projects/DeleteProjectDialog";
import { useProjects } from "../projects/ProjectsContext";
import { projectLabel } from "../lib/caseFileFields";
import { relativeTime } from "../lib/relativeTime";
import type { CaseFile } from "../types";
import "./RecentChats.css";

const VISIBLE_COUNT = 8;

interface Props {
  activeSessionId: string | null;
  onOpenChat: (caseFile: CaseFile) => void;
  onNewChat: () => void;
  onViewAll: () => void;
  /** Called after a delete, so the app can clear the active project. */
  onDeleted: (sessionId: string) => void;
}

// The chat-history rail, in the shape people already know from Claude and
// ChatGPT: a "New chat" action, then your recent conversations, newest
// first, one click away from being continued. Before this, leaving the
// Overview page stranded the conversation - the only way back was the
// Project History table, which opens the Case File, not the chat.
export function RecentChats({ activeSessionId, onOpenChat, onNewChat, onViewAll, onDeleted }: Props) {
  const { user } = useAuth();
  const { projects, loading, error } = useProjects();
  const [loginOpen, setLoginOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<CaseFile | null>(null);

  // Anonymous case files have no owner, so there is nothing to list - be
  // honest about why rather than showing a permanently empty section.
  if (!user) {
    return (
      <div className="ds-recent-chats">
        <div className="ds-recent-chats__heading">Chats</div>
        <p className="ds-recent-chats__signed-out">
          <button type="button" className="ds-recent-chats__link" onClick={() => setLoginOpen(true)}>
            Sign in
          </button>{" "}
          to keep your chats and pick them up later.
        </p>
        {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
      </div>
    );
  }

  const visible = (projects ?? []).slice(0, VISIBLE_COUNT);

  return (
    <div className="ds-recent-chats">
      <div className="ds-recent-chats__heading">Chats</div>

      <button type="button" className="ds-recent-chats__new" onClick={onNewChat}>
        <Plus className="ds-recent-chats__new-icon" aria-hidden="true" />
        <span>New chat</span>
      </button>

      {loading && projects === null && <p className="ds-recent-chats__note">Loading…</p>}
      {error && (
        <p className="ds-recent-chats__note ds-recent-chats__note--error" role="alert">
          {error}
        </p>
      )}
      {!loading && projects !== null && projects.length === 0 && (
        <p className="ds-recent-chats__note">No chats yet. Start one on the Overview page.</p>
      )}

      <ul className="ds-recent-chats__list">
        {visible.map((project) => {
          const isActive = project.session_id === activeSessionId;
          const label = projectLabel(project);
          return (
            <li key={project.session_id} className={`ds-recent-chats__row${isActive ? " ds-recent-chats__row--active" : ""}`}>
              <button
                type="button"
                className="ds-recent-chats__item"
                onClick={() => onOpenChat(project)}
                aria-current={isActive ? "true" : undefined}
                title={label}
              >
                <MessageSquare className="ds-recent-chats__item-icon" aria-hidden="true" />
                <span className="ds-recent-chats__item-text">
                  <span className="ds-recent-chats__item-title">{label}</span>
                  <span className="ds-recent-chats__item-meta">{relativeTime(project.updated_at)}</span>
                </span>
              </button>
              <button
                type="button"
                className="ds-recent-chats__delete"
                onClick={() => setPendingDelete(project)}
                aria-label={`Delete ${label}`}
                title="Delete chat"
              >
                <Trash2 aria-hidden="true" />
              </button>
            </li>
          );
        })}
      </ul>

      {projects !== null && projects.length > VISIBLE_COUNT && (
        <button type="button" className="ds-recent-chats__view-all" onClick={onViewAll}>
          All {projects.length} projects
        </button>
      )}

      {pendingDelete && (
        <DeleteProjectDialog project={pendingDelete} onClose={() => setPendingDelete(null)} onDeleted={onDeleted} />
      )}
    </div>
  );
}
