import { Trash2, UserPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { Button } from "../../design-system/components/Button";
import { Card } from "../../design-system/components/Card";
import type { CaseFileGrant } from "../../types";
import "./SharePanel.css";

interface Props {
  sessionId: string;
}

// Owner-only. A reviewer gets read access plus the ability to record a
// verdict, and nothing else - they cannot edit a field, continue the
// conversation, delete the project, or share it onward. That restriction
// is what makes their verdict worth anything, so the panel says it out
// loud rather than leaving the owner to guess what they just granted.
export function SharePanel({ sessionId }: Props) {
  const [grants, setGrants] = useState<CaseFileGrant[] | null>(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .listShares(sessionId)
      .then(setGrants)
      .catch(() => setGrants([]));
  }, [sessionId]);

  useEffect(load, [load]);

  const share = async () => {
    const trimmed = email.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      await api.shareCaseFile(sessionId, trimmed);
      setEmail("");
      load();
    } catch (err) {
      // The 404 here is meaningful and specific ("no account for that
      // address"), so show what the backend actually said rather than a
      // generic failure the owner can't act on.
      setError(
        err instanceof ApiError && err.status === 404
          ? `No account found for ${trimmed}. They need to sign up first.`
          : err instanceof ApiError && err.status === 422
            ? "That address can't be added — you already own this project."
            : "Could not share this project.",
      );
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (grant: CaseFileGrant) => {
    setBusy(true);
    setError(null);
    try {
      await api.revokeShare(sessionId, grant.granted_to_user_id);
      load();
    } catch {
      setError("Could not remove that reviewer.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Reviewers">
      <p className="ds-share-panel__lead">
        A reviewer can read this project, download the handoff pack and record a verdict. They cannot edit any fact,
        continue the conversation, delete the project, or share it with anyone else.
      </p>

      <div className="ds-share-panel__form">
        <input
          type="email"
          className="ds-share-panel__input"
          placeholder="reviewer@example.com"
          aria-label="Reviewer's email address"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void share();
          }}
          disabled={busy}
        />
        <Button variant="secondary" size="sm" icon={<UserPlus />} onClick={() => void share()} disabled={busy || !email.trim()}>
          Add
        </Button>
      </div>

      {error && (
        <p className="ds-share-panel__error" role="alert">
          {error}
        </p>
      )}

      {grants !== null && grants.length === 0 && (
        <p className="ds-share-panel__lead">Not shared with anyone yet.</p>
      )}

      {grants !== null && grants.length > 0 && (
        <ul className="ds-share-panel__list">
          {grants.map((grant) => (
            <li key={grant.id} className="ds-share-panel__row">
              <span className="ds-share-panel__email">{grant.granted_to_email}</span>
              <Button
                variant="ghost"
                size="sm"
                icon={<Trash2 />}
                iconOnly
                aria-label={`Remove ${grant.granted_to_email}`}
                title="Remove reviewer"
                onClick={() => void revoke(grant)}
                disabled={busy}
              />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
