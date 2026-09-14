import { UserCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { Button } from "../../design-system/components/Button";
import { Card } from "../../design-system/components/Card";
import { parseApiTimestamp, relativeTime } from "../../lib/relativeTime";
import type { Assignment, OrganisationMember, OrganisationSummary } from "../../types";
import "./SharePanel.css";

interface Props {
  sessionId: string;
  /** Only an owner or a team administrator may change an assignment. */
  canAssign: boolean;
}

// Who owes this review, and by when.
//
// The due date is ADVISORY and the panel says so. Nothing in this product
// enforces one or acts when it passes - the queue marks the case overdue
// and that is the whole of it. Implying otherwise in a compliance tool
// would be worse than not having due dates at all.
export function AssignmentPanel({ sessionId, canAssign }: Props) {
  const [assignment, setAssignment] = useState<Assignment | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [candidates, setCandidates] = useState<OrganisationMember[]>([]);
  const [userId, setUserId] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .getAssignment(sessionId)
      .then((current) => {
        setAssignment(current);
        setUserId(current?.assigned_to_user_id ?? "");
        // An ISO instant trimmed to what <input type="date"> wants. Only
        // the date is offered: an hour-precision deadline on a review
        // that takes days would be false precision.
        setDueAt(current?.due_at ? parseApiTimestamp(current.due_at).toISOString().slice(0, 10) : "");
      })
      .catch(() => setAssignment(null))
      .finally(() => setLoaded(true));
  }, [sessionId]);

  useEffect(load, [load]);

  // Who can be assigned: the members of every team this account is in.
  // The server independently refuses anyone who cannot already read the
  // case, so this list is a convenience, never the access rule.
  useEffect(() => {
    if (!canAssign) return;
    let cancelled = false;
    void api
      .listOrganisations()
      .then(async (organisations: OrganisationSummary[]) => {
        const lists = await Promise.all(
          organisations.map((summary) =>
            api.listMembers(summary.organisation.id).catch(() => [] as OrganisationMember[]),
          ),
        );
        if (cancelled) return;
        const seen = new Set<string>();
        const unique: OrganisationMember[] = [];
        for (const member of lists.flat()) {
          if (seen.has(member.user_id)) continue;
          seen.add(member.user_id);
          unique.push(member);
        }
        unique.sort((a, b) => a.email.localeCompare(b.email));
        setCandidates(unique);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [canAssign]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      // Midday UTC rather than midnight: a date-only deadline read back in
      // a timezone behind UTC would otherwise land on the previous day.
      const due = dueAt ? new Date(`${dueAt}T12:00:00Z`).toISOString() : null;
      const saved = await api.setAssignment(sessionId, userId || null, due, note);
      setAssignment(saved);
      setNote("");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 422
          ? "That person can't see this project, so it can't be assigned to them. Add them to a team it belongs to first."
          : "Could not save the assignment.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (!loaded) return null;

  const overdue = assignment?.due_at ? parseApiTimestamp(assignment.due_at).getTime() < Date.now() : false;

  return (
    <Card title="Assignment">
      {assignment?.assigned_to_email ? (
        <p className="ds-share-panel__lead">
          Assigned to <strong>{assignment.assigned_to_email}</strong>
          {assignment.due_at && (
            <>
              , due {relativeTime(assignment.due_at)}
              {overdue && " — past due"}
            </>
          )}
          .{assignment.note && ` “${assignment.note}”`}
        </p>
      ) : (
        <p className="ds-share-panel__lead">
          {assignment ? "Explicitly unassigned." : "Nobody has been asked to review this yet."}
        </p>
      )}

      {!canAssign ? (
        <p className="ds-share-panel__lead">
          Only this project's owner, or an administrator of a team it belongs to, can change who it's
          assigned to.
        </p>
      ) : (
        <>
          <label className="ds-share-panel__field">
            <span>Assign to</span>
            <select
              className="ds-share-panel__input"
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              disabled={busy}
            >
              <option value="">Nobody (unassign)</option>
              {candidates.map((member) => (
                <option key={member.user_id} value={member.user_id}>
                  {member.email}
                </option>
              ))}
            </select>
          </label>

          <label className="ds-share-panel__field">
            <span>Due date (optional)</span>
            <input
              type="date"
              className="ds-share-panel__input"
              value={dueAt}
              onChange={(event) => setDueAt(event.target.value)}
              disabled={busy}
            />
          </label>

          <label className="ds-share-panel__field">
            <span>Note (optional)</span>
            <input
              type="text"
              className="ds-share-panel__input"
              placeholder="What you'd like them to check"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              disabled={busy}
            />
          </label>

          {error && (
            <p className="ds-share-panel__error" role="alert">
              {error}
            </p>
          )}

          <Button variant="secondary" size="sm" icon={<UserCheck />} onClick={() => void save()} disabled={busy}>
            {busy ? "Saving…" : "Save assignment"}
          </Button>

          {/* Said out loud because a compliance tool that implied it
              enforced deadlines would be making a promise it does not keep. */}
          <p className="ds-share-panel__lead ds-share-panel__footnote">
            A due date is a note to the people involved. Nothing here enforces it or acts when it
            passes — the queue marks the case overdue, and that is all.
          </p>
        </>
      )}
    </Card>
  );
}
