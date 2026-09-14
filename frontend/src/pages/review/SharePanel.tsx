import { Check, Copy, Link2, Trash2, UserPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { Button } from "../../design-system/components/Button";
import { Card } from "../../design-system/components/Card";
import { relativeTime } from "../../lib/relativeTime";
import type { CaseFileGrant, CaseFileInvite } from "../../types";
import "./SharePanel.css";

interface Props {
  sessionId: string;
}

// Owner-only. A reviewer gets read access plus the ability to record a
// verdict, and nothing else - they cannot edit a field, continue the
// conversation, delete the project, or share it onward. That restriction
// is what makes their verdict worth anything, so the panel says it out
// loud rather than leaving the owner to guess what they just granted.
//
// Two ways in, because the person you need to review something usually
// doesn't have an account yet: adding by address works only for someone who
// does, and an invite LINK works for anyone. The link is shown here, once,
// rather than mailed - the owner is already authorised to share this
// project, so handing it to them is secure and spares the product a mail
// transport to operate.
export function SharePanel({ sessionId }: Props) {
  const [grants, setGrants] = useState<CaseFileGrant[] | null>(null);
  const [invites, setInvites] = useState<CaseFileInvite[]>([]);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Set when adding by address failed because there is no account - the
  // one case where an invite link is the answer, offered as a button so
  // the owner doesn't have to work that out for themselves.
  const [offerInvite, setOfferInvite] = useState<string | null>(null);
  // The freshly-minted link. Held in state and nowhere else: the token is
  // stored hashed server-side, so once this is dismissed it cannot be
  // shown again, only revoked and reissued.
  const [freshLink, setFreshLink] = useState<{ email: string; url: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    api
      .listShares(sessionId)
      .then(setGrants)
      .catch(() => setGrants([]));
    api
      .listInvites(sessionId)
      .then(setInvites)
      .catch(() => setInvites([]));
  }, [sessionId]);

  useEffect(load, [load]);

  const reset = () => {
    setError(null);
    setOfferInvite(null);
  };

  const share = async () => {
    const trimmed = email.trim();
    if (!trimmed) return;
    setBusy(true);
    reset();
    try {
      await api.shareCaseFile(sessionId, trimmed);
      setEmail("");
      setFreshLink(null);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setOfferInvite(trimmed);
        setError(`No account yet for ${trimmed}. Send them an invite link instead.`);
      } else {
        setError(
          err instanceof ApiError && err.status === 422
            ? "That address can't be added — you already own this project."
            : "Could not share this project.",
        );
      }
    } finally {
      setBusy(false);
    }
  };

  const invite = async (address: string) => {
    setBusy(true);
    reset();
    try {
      const created = await api.createInvite(sessionId, address);
      if (created.invite_url) setFreshLink({ email: address, url: created.invite_url });
      setEmail("");
      setCopied(false);
      load();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 422
          ? "That address can't be invited — they already have access, or you own this project."
          : "Could not create an invitation.",
      );
    } finally {
      setBusy(false);
    }
  };

  const copyLink = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      // Clipboard blocked (no permission, or an insecure origin). The link
      // is on screen and selectable, so this is a missing convenience
      // rather than a dead end - say nothing and let them select it.
    }
  };

  const revokeGrant = async (grant: CaseFileGrant) => {
    setBusy(true);
    reset();
    try {
      await api.revokeShare(sessionId, grant.granted_to_user_id);
      load();
    } catch {
      setError("Could not remove that reviewer.");
    } finally {
      setBusy(false);
    }
  };

  const revokeInvite = async (pending: CaseFileInvite) => {
    setBusy(true);
    reset();
    try {
      await api.revokeInvite(sessionId, pending.invited_email);
      if (freshLink?.email === pending.invited_email) setFreshLink(null);
      load();
    } catch {
      setError("Could not cancel that invitation.");
    } finally {
      setBusy(false);
    }
  };

  // An accepted invite is already represented by a grant in the list above,
  // so showing it here too would double-count the same reviewer.
  const pending = invites.filter((item) => item.accepted_at === null);

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
          onChange={(event) => {
            setEmail(event.target.value);
            reset();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") void share();
          }}
          disabled={busy}
        />
        <Button variant="secondary" size="sm" icon={<UserPlus />} onClick={() => void share()} disabled={busy || !email.trim()}>
          Add
        </Button>
        <Button
          variant="ghost"
          size="sm"
          icon={<Link2 />}
          onClick={() => void invite(email.trim())}
          disabled={busy || !email.trim()}
          title="Create a link they can use to sign up and accept"
        >
          Invite by link
        </Button>
      </div>

      {error && (
        <p className="ds-share-panel__error" role="alert">
          {error}
          {offerInvite && (
            <Button variant="secondary" size="sm" icon={<Link2 />} onClick={() => void invite(offerInvite)} disabled={busy}>
              Create invite link
            </Button>
          )}
        </p>
      )}

      {freshLink && (
        <div className="ds-share-panel__link" role="status">
          <p className="ds-share-panel__link-lead">
            Send this link to <strong>{freshLink.email}</strong>. It is shown once — copy it now. It works for two
            weeks, once, and anyone holding it can accept, so pass it on privately.
          </p>
          <div className="ds-share-panel__link-row">
            <code className="ds-share-panel__link-url">{freshLink.url}</code>
            <Button
              variant="secondary"
              size="sm"
              icon={copied ? <Check /> : <Copy />}
              onClick={() => void copyLink(freshLink.url)}
            >
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <button type="button" className="ds-share-panel__dismiss" onClick={() => setFreshLink(null)}>
            Done
          </button>
        </div>
      )}

      {grants !== null && grants.length === 0 && pending.length === 0 && (
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
                onClick={() => void revokeGrant(grant)}
                disabled={busy}
              />
            </li>
          ))}
        </ul>
      )}

      {pending.length > 0 && (
        <>
          <p className="ds-share-panel__section">Invited, not yet accepted</p>
          <ul className="ds-share-panel__list">
            {pending.map((item) => (
              <li key={item.invited_email} className="ds-share-panel__row">
                <span className="ds-share-panel__email">{item.invited_email}</span>
                <span className="ds-share-panel__expiry">expires {relativeTime(item.expires_at)}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Trash2 />}
                  iconOnly
                  aria-label={`Cancel the invitation to ${item.invited_email}`}
                  title="Cancel invitation"
                  onClick={() => void revokeInvite(item)}
                  disabled={busy}
                />
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
