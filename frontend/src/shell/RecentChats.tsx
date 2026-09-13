import { MessageSquare, Pin, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { LoginModal } from "../auth/LoginModal";
import { DeleteProjectDialog } from "../projects/DeleteProjectDialog";
import { RenameProjectDialog } from "../projects/RenameProjectDialog";
import { useProjects } from "../projects/ProjectsContext";
import { usePinnedChats } from "../projects/usePinnedChats";
import { projectLabel } from "../lib/caseFileFields";
import { relativeTime } from "../lib/relativeTime";
import { ChatRowMenu } from "./ChatRowMenu";
import { groupChatsByRecency } from "./chatGroups";
import type { CaseFile } from "../types";
import "./RecentChats.css";

// How many unpinned chats the rail shows before deferring to the full
// Project History table. Pinned chats are always shown - that is the point
// of pinning one.
const VISIBLE_COUNT = 8;
// Searching looks across every project the account has, but the rail is
// still a rail: past this many matches, narrow the search.
const SEARCH_RESULT_LIMIT = 20;

interface Props {
  activeSessionId: string | null;
  onOpenChat: (caseFile: CaseFile) => void;
  onNewChat: () => void;
  onViewAll: () => void;
  /** Called after a delete, so the app can clear the active project. */
  onDeleted: (sessionId: string) => void;
  /** Called after a rename, so the header and inspector update too. */
  onRenamed: (caseFile: CaseFile) => void;
}

// The chat-history rail, in the shape people already know from Claude and
// ChatGPT: a "New chat" action, a search box, pinned chats, then recent
// conversations grouped by when they were last touched - each one click
// away from being continued. Before this, leaving the Overview page
// stranded the conversation: the only way back was the Project History
// table, which opens the Case File rather than the chat.
export function RecentChats({ activeSessionId, onOpenChat, onNewChat, onViewAll, onDeleted, onRenamed }: Props) {
  const { user } = useAuth();
  const { projects, titles, loading, error } = useProjects();
  const { isPinned, toggle: togglePin } = usePinnedChats(user?.id ?? null);
  const [loginOpen, setLoginOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [pendingDelete, setPendingDelete] = useState<CaseFile | null>(null);
  const [pendingRename, setPendingRename] = useState<CaseFile | null>(null);

  const labelFor = useMemo(
    () => (project: CaseFile) => projectLabel(project, titles[project.session_id]),
    [titles],
  );

  const trimmedQuery = query.trim().toLowerCase();

  const { pinned, recent, hiddenCount, searchOverflow } = useMemo(() => {
    const all = projects ?? [];

    if (trimmedQuery) {
      // Search covers every project the account has, not just the ones the
      // rail happens to be showing - otherwise it would only ever find
      // what is already on screen.
      const matches = all.filter((project) => labelFor(project).toLowerCase().includes(trimmedQuery));
      return {
        pinned: [] as CaseFile[],
        recent: matches.slice(0, SEARCH_RESULT_LIMIT),
        hiddenCount: 0,
        searchOverflow: Math.max(0, matches.length - SEARCH_RESULT_LIMIT),
      };
    }

    const pinnedProjects = all.filter((project) => isPinned(project.session_id));
    const rest = all.filter((project) => !isPinned(project.session_id));
    return {
      pinned: pinnedProjects,
      recent: rest.slice(0, VISIBLE_COUNT),
      hiddenCount: Math.max(0, rest.length - VISIBLE_COUNT),
      searchOverflow: 0,
    };
  }, [projects, trimmedQuery, isPinned, labelFor]);

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

  const total = projects?.length ?? 0;

  const renderRow = (project: CaseFile) => {
    const isActive = project.session_id === activeSessionId;
    const label = labelFor(project);
    const pinnedRow = isPinned(project.session_id);
    return (
      <li key={project.session_id} className={`ds-recent-chats__row${isActive ? " ds-recent-chats__row--active" : ""}`}>
        <button
          type="button"
          className="ds-recent-chats__item"
          onClick={() => onOpenChat(project)}
          aria-current={isActive ? "true" : undefined}
          title={label}
        >
          {pinnedRow ? (
            <Pin className="ds-recent-chats__item-icon" aria-label="Pinned" />
          ) : (
            <MessageSquare className="ds-recent-chats__item-icon" aria-hidden="true" />
          )}
          <span className="ds-recent-chats__item-text">
            <span className="ds-recent-chats__item-title">{label}</span>
            <span className="ds-recent-chats__item-meta">{relativeTime(project.updated_at)}</span>
          </span>
        </button>
        <ChatRowMenu
          label={label}
          pinned={pinnedRow}
          onTogglePin={() => togglePin(project.session_id)}
          onRename={() => setPendingRename(project)}
          onDelete={() => setPendingDelete(project)}
        />
      </li>
    );
  };

  return (
    <div className="ds-recent-chats">
      <div className="ds-recent-chats__heading">Chats</div>

      <button type="button" className="ds-recent-chats__new" onClick={onNewChat}>
        <Plus className="ds-recent-chats__new-icon" aria-hidden="true" />
        <span>New chat</span>
      </button>

      {total > VISIBLE_COUNT && (
        <div className="ds-recent-chats__search">
          <Search className="ds-recent-chats__search-icon" aria-hidden="true" />
          <input
            type="search"
            className="ds-recent-chats__search-input"
            placeholder="Search chats"
            aria-label="Search chats"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      )}

      {loading && projects === null && <p className="ds-recent-chats__note">Loading…</p>}
      {error && (
        <p className="ds-recent-chats__note ds-recent-chats__note--error" role="alert">
          {error}
        </p>
      )}
      {!loading && projects !== null && projects.length === 0 && (
        <p className="ds-recent-chats__note">No chats yet. Start one on the Overview page.</p>
      )}
      {trimmedQuery && recent.length === 0 && projects !== null && projects.length > 0 && (
        <p className="ds-recent-chats__note">No chats match “{query.trim()}”.</p>
      )}

      <div className="ds-recent-chats__scroll">
        {pinned.length > 0 && (
          <section className="ds-recent-chats__group">
            <h3 className="ds-recent-chats__group-label">Pinned</h3>
            <ul className="ds-recent-chats__list">{pinned.map(renderRow)}</ul>
          </section>
        )}

        {trimmedQuery ? (
          <ul className="ds-recent-chats__list">{recent.map(renderRow)}</ul>
        ) : (
          groupChatsByRecency(recent).map((group) => (
            <section key={group.key} className="ds-recent-chats__group">
              <h3 className="ds-recent-chats__group-label">{group.label}</h3>
              <ul className="ds-recent-chats__list">{group.projects.map(renderRow)}</ul>
            </section>
          ))
        )}
      </div>

      {searchOverflow > 0 && (
        <p className="ds-recent-chats__note">{searchOverflow} more match. Narrow the search to see them.</p>
      )}

      {!trimmedQuery && hiddenCount > 0 && (
        <button type="button" className="ds-recent-chats__view-all" onClick={onViewAll}>
          All {total} projects
        </button>
      )}

      {pendingDelete && (
        <DeleteProjectDialog project={pendingDelete} onClose={() => setPendingDelete(null)} onDeleted={onDeleted} />
      )}
      {pendingRename && (
        <RenameProjectDialog
          project={pendingRename}
          chatTitle={titles[pendingRename.session_id]}
          onClose={() => setPendingRename(null)}
          onRenamed={onRenamed}
        />
      )}
    </div>
  );
}
