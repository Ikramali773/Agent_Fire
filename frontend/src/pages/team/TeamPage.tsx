import { Plus, Trash2, UserPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { LoginModal } from "../../auth/LoginModal";
import { Button } from "../../design-system/components/Button";
import { Card } from "../../design-system/components/Card";
import { relativeTime } from "../../lib/relativeTime";
import { EmptyState } from "../../design-system/components/EmptyState";
import type {
  CaseFile,
  MemberRole,
  OrganisationCaseFile,
  OrganisationMember,
  OrganisationSummary,
} from "../../types";
import "./TeamPage.css";

interface Props {
  caseFile: CaseFile | null;
}

// Teams. Sharing one project with one person at a time does not survive
// six colleagues and forty projects: every new project means six more
// shares, every new colleague means forty, and the day someone leaves you
// have to remember all of them.
//
// What a team deliberately does NOT grant is WRITE. Members read, record
// verdicts, and can be assigned a review - exactly the reviewer capability
// that already existed, because the reason for it has not changed: a
// verdict on facts the reviewer could have edited is worth nothing, and
// that does not stop being true because the reviewer is a colleague.
export function TeamPage({ caseFile }: Props) {
  const { user } = useAuth();
  const [loginOpen, setLoginOpen] = useState(false);
  const [organisations, setOrganisations] = useState<OrganisationSummary[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [members, setMembers] = useState<OrganisationMember[]>([]);
  const [projects, setProjects] = useState<OrganisationCaseFile[]>([]);
  const [newName, setNewName] = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadOrganisations = useCallback(() => {
    if (!user) {
      setOrganisations(null);
      return;
    }
    api
      .listOrganisations()
      .then((list) => {
        setOrganisations(list);
        setSelectedId((current) => current ?? list[0]?.organisation.id ?? null);
      })
      .catch(() => setOrganisations([]));
  }, [user]);

  useEffect(loadOrganisations, [loadOrganisations]);

  const loadDetail = useCallback(() => {
    if (!selectedId) {
      setMembers([]);
      setProjects([]);
      return;
    }
    api.listMembers(selectedId).then(setMembers).catch(() => setMembers([]));
    api.listOrganisationCaseFiles(selectedId).then(setProjects).catch(() => setProjects([]));
  }, [selectedId]);

  useEffect(loadDetail, [loadDetail]);

  if (!user) {
    return (
      <div className="ds-team-page">
        <EmptyState
          title="Teams need an account"
          description="A team is a group of accounts, so there is nothing to build one out of until you sign in."
          action={
            <Button variant="primary" onClick={() => setLoginOpen(true)}>
              Sign in
            </Button>
          }
        />
        {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
      </div>
    );
  }

  const selected = organisations?.find((item) => item.organisation.id === selectedId) ?? null;
  const isAdmin = selected?.role === "admin";
  const isCreator = selected?.organisation.created_by_user_id === user.id;
  const activeShared =
    caseFile !== null && projects.some((item) => item.session_id === caseFile.session_id);
  const ownsActive = caseFile !== null && caseFile.owner_user_id === user.id;

  const run = async (action: () => Promise<unknown>, fallback: string) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      loadOrganisations();
      loadDetail();
    } catch (err) {
      setError(err instanceof ApiError ? err.message.replace(/^\d+ [^:]*:\s*/, "") : fallback);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ds-team-page">
      <Card title="Your teams">
        <p className="ds-team-page__lead">
          A project shared with a team is readable by every member, and a member who leaves loses
          that access in one step rather than one project at a time. Members can read a project,
          download its handoff pack and record a verdict — they cannot edit any fact, continue the
          conversation, delete it, or share it onward.
        </p>

        {organisations !== null && organisations.length === 0 && (
          <p className="ds-team-page__lead">You are not in a team yet.</p>
        )}

        {organisations !== null && organisations.length > 0 && (
          <ul className="ds-team-page__list">
            {organisations.map((summary) => (
              <li key={summary.organisation.id}>
                <button
                  type="button"
                  className={`ds-team-page__row${
                    summary.organisation.id === selectedId ? " ds-team-page__row--active" : ""
                  }`}
                  onClick={() => setSelectedId(summary.organisation.id)}
                >
                  <span className="ds-team-page__name">{summary.organisation.name}</span>
                  <span className="ds-team-page__meta">
                    {summary.member_count} member{summary.member_count === 1 ? "" : "s"} · you are{" "}
                    {summary.role === "admin" ? "an administrator" : "a member"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="ds-team-page__form">
          <input
            type="text"
            className="ds-team-page__input"
            placeholder="New team name"
            aria-label="New team name"
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            disabled={busy}
          />
          <Button
            variant="secondary"
            size="sm"
            icon={<Plus />}
            disabled={busy || !newName.trim()}
            onClick={() =>
              void run(async () => {
                const created = await api.createOrganisation(newName.trim());
                setNewName("");
                setSelectedId(created.id);
              }, "Could not create that team.")
            }
          >
            Create
          </Button>
        </div>
      </Card>

      {error && (
        <p className="ds-team-page__error" role="alert">
          {error}
        </p>
      )}

      {selected && (
        <Card title={`${selected.organisation.name} · members`}>
          <ul className="ds-team-page__list">
            {members.map((member) => (
              <li key={member.user_id} className="ds-team-page__member">
                <span className="ds-team-page__name">{member.email}</span>
                <span className="ds-team-page__meta">
                  {member.user_id === selected.organisation.created_by_user_id
                    ? "creator · administrator"
                    : member.role === "admin"
                      ? "administrator"
                      : "member"}
                </span>
                {isAdmin && member.user_id !== selected.organisation.created_by_user_id && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        void run(
                          () =>
                            api.setMemberRole(
                              selected.organisation.id,
                              member.user_id,
                              (member.role === "admin" ? "member" : "admin") as MemberRole,
                            ),
                          "Could not change that role.",
                        )
                      }
                      disabled={busy}
                    >
                      {member.role === "admin" ? "Make member" : "Make admin"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<Trash2 />}
                      iconOnly
                      aria-label={`Remove ${member.email}`}
                      onClick={() =>
                        void run(
                          () => api.removeMember(selected.organisation.id, member.user_id),
                          "Could not remove that member.",
                        )
                      }
                      disabled={busy}
                    />
                  </>
                )}
                {!isAdmin && member.user_id === user.id && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      void run(async () => {
                        await api.removeMember(selected.organisation.id, user.id);
                        setSelectedId(null);
                      }, "Could not leave that team.")
                    }
                    disabled={busy}
                  >
                    Leave
                  </Button>
                )}
              </li>
            ))}
          </ul>

          {isAdmin && (
            <div className="ds-team-page__form">
              <input
                type="email"
                className="ds-team-page__input"
                placeholder="colleague@example.com"
                aria-label="Colleague's email address"
                value={memberEmail}
                onChange={(event) => setMemberEmail(event.target.value)}
                disabled={busy}
              />
              <Button
                variant="secondary"
                size="sm"
                icon={<UserPlus />}
                disabled={busy || !memberEmail.trim()}
                onClick={() =>
                  void run(async () => {
                    await api.addMember(selected.organisation.id, memberEmail.trim());
                    setMemberEmail("");
                  }, "Could not add that person.")
                }
              >
                Add
              </Button>
            </div>
          )}

          {/* Said plainly because it is the one thing people get wrong
              about teams: there is no mail transport here, so a colleague
              who has not signed up cannot be added. The per-project invite
              link is the route for them. */}
          {isAdmin && (
            <p className="ds-team-page__footnote">
              They need an account already. For someone who hasn't signed up, send them an invite
              link from a project's Reviewers panel instead.
            </p>
          )}
        </Card>
      )}

      {selected && (
        <Card title={`${selected.organisation.name} · projects`}>
          {projects.length === 0 ? (
            <p className="ds-team-page__lead">No project is shared with this team yet.</p>
          ) : (
            <ul className="ds-team-page__list">
              {projects.map((item) => (
                <li key={item.session_id} className="ds-team-page__member">
                  <span className="ds-team-page__name">{item.project_name}</span>
                  {/* What makes a row worth looking at first. Not a
                      compliance status - the engine flagged it, which is a
                      different statement from "this building fails". */}
                  {item.requires_review && (
                    <span className="ds-team-page__meta">needs review</span>
                  )}
                  <span className="ds-team-page__meta">
                    updated {relativeTime(item.updated_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {caseFile && ownsActive && (
            <Button
              variant="secondary"
              size="sm"
              disabled={busy}
              onClick={() =>
                void run(
                  () =>
                    activeShared
                      ? api.removeCaseFileFromOrganisation(selected.organisation.id, caseFile.session_id)
                      : api.addCaseFileToOrganisation(selected.organisation.id, caseFile.session_id),
                  "Could not change what this team can see.",
                )
              }
            >
              {activeShared
                ? `Stop sharing “${caseFile.project_name || "this project"}”`
                : `Share “${caseFile.project_name || "this project"}” with this team`}
            </Button>
          )}

          {caseFile && !ownsActive && (
            <p className="ds-team-page__footnote">
              Only a project's owner can share it with a team — administering a team is not a way to
              pull in someone else's work.
            </p>
          )}

          {!caseFile && (
            <p className="ds-team-page__footnote">
              Open a project to share it with this team.
            </p>
          )}
        </Card>
      )}

      {selected && isCreator && (
        <Card title="Danger zone">
          <p className="ds-team-page__lead">
            Deleting a team takes away its members' access. It does not delete a single project — a
            team is a way of sharing work, never where it lives.
          </p>
          <Button
            variant="ghost"
            size="sm"
            icon={<Trash2 />}
            disabled={busy}
            onClick={() =>
              void run(async () => {
                await api.deleteOrganisation(selected.organisation.id);
                setSelectedId(null);
              }, "Could not delete that team.")
            }
          >
            Delete {selected.organisation.name}
          </Button>
        </Card>
      )}
    </div>
  );
}
