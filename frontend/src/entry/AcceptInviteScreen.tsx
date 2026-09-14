import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { authErrorMessage } from "../auth/errors";
import { LoginModal } from "../auth/LoginModal";
import { Button } from "../design-system/components/Button";
import { parseApiTimestamp, relativeTime } from "../lib/relativeTime";
import type { InvitePreview } from "../types";
import "../auth/LoginModal.css";
import "./LinkScreen.css";

interface Props {
  token: string;
  // The reviewer is in - open the project they were invited to.
  onAccepted: (sessionId: string) => void;
  // Not accepting (already used, broken, or declined) - carry on into the
  // ordinary app.
  onDismiss: () => void;
}

// The full-screen step behind an `?invite=<token>` link. Shows what the
// invitation is BEFORE asking for an account: being told to sign up with no
// idea what for is how an invitation gets closed.
export function AcceptInviteScreen({ token, onAccepted, onDismiss }: Props) {
  const { user, loading: authLoading } = useAuth();
  const [preview, setPreview] = useState<InvitePreview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);
  const [signInOpen, setSignInOpen] = useState(false);

  useEffect(() => {
    api
      .previewInvite(token)
      .then(setPreview)
      .catch((err: unknown) =>
        setLoadError(authErrorMessage(err, "This invitation link is not valid.")),
      );
  }, [token]);

  const accept = async () => {
    setAccepting(true);
    setError(null);
    try {
      const invite = await api.acceptInvite(token);
      onAccepted(invite.session_id);
    } catch (err) {
      setError(authErrorMessage(err, "Could not accept this invitation."));
    } finally {
      setAccepting(false);
    }
  };

  if (loadError) {
    return (
      <Screen title="That invitation didn't work">
        <p className="ds-link-screen__lead">{loadError}</p>
        <p className="ds-link-screen__lead">
          Invitations expire after two weeks and can be cancelled by the project owner. Ask whoever sent it for a fresh
          link.
        </p>
        <Button variant="secondary" onClick={onDismiss}>
          Continue to the app
        </Button>
      </Screen>
    );
  }

  if (!preview || authLoading) {
    return (
      <Screen title="Checking your invitation…">
        <p className="ds-link-screen__lead">One moment.</p>
      </Screen>
    );
  }

  if (preview.already_accepted) {
    return (
      <Screen title="Already accepted">
        <p className="ds-link-screen__lead">
          This invitation has been used. If it was you, sign in and you'll find <strong>{preview.project_name}</strong>{" "}
          in your review queue.
        </p>
        <Button variant="secondary" onClick={onDismiss}>
          Continue to the app
        </Button>
      </Screen>
    );
  }

  const expired = parseApiTimestamp(preview.expires_at).getTime() < Date.now();

  return (
    <Screen title="You've been asked to review a project">
      <div className="ds-link-screen__meta">
        <span>
          Project: <strong>{preview.project_name}</strong>
        </span>
        <span>
          Invited by: <strong>{preview.invited_by_email}</strong>
        </span>
        <span>
          Sent to: <strong>{preview.invited_email}</strong>
        </span>
        <span>{expired ? "This link has expired." : `Link expires ${relativeTime(preview.expires_at)}.`}</span>
      </div>

      {/* Says exactly what accepting grants, because a reviewer signing an
          NBCS verdict needs to know the limits of what they're looking at -
          and because the owner was told the same thing when they invited. */}
      <p className="ds-link-screen__lead">
        Accepting gives you read access to this project's case file, its handoff pack, and the ability to record a
        review verdict. You will not be able to edit any fact, continue its conversation, or share it onward.
      </p>

      {expired ? (
        <Button variant="secondary" onClick={onDismiss}>
          Continue to the app
        </Button>
      ) : user ? (
        <>
          <p className="ds-link-screen__lead">
            You're signed in as <strong>{user.email}</strong>. Accepting will attach this project to that account.
          </p>
          {error && (
            <div className="ds-login-modal__error" role="alert">
              {error}
            </div>
          )}
          <Button variant="primary" onClick={() => void accept()} disabled={accepting}>
            {accepting ? "Accepting…" : "Accept and open the project"}
          </Button>
          <button type="button" className="ds-login-modal__switch" onClick={onDismiss}>
            Not now
          </button>
        </>
      ) : (
        <>
          {/* An account is required on purpose: a compliance verdict has to
              be attributable to a person, and "whoever had the link" is not
              one. Signing up with a different address than the invitation
              was sent to is allowed - a consultant may well have one. */}
          <p className="ds-link-screen__lead">
            Sign in or create an account to accept. A review verdict has to be attributable to a person, so this step
            can't be skipped.
          </p>
          <Button variant="primary" onClick={() => setSignInOpen(true)}>
            Sign in or create an account
          </Button>
          <button type="button" className="ds-login-modal__switch" onClick={onDismiss}>
            Not now
          </button>
          {signInOpen && <LoginModal onClose={() => setSignInOpen(false)} />}
        </>
      )}
    </Screen>
  );
}

function Screen({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="ds-link-screen">
      <div className="ds-link-screen__card">
        <h1 className="ds-link-screen__title">{title}</h1>
        {children}
      </div>
    </div>
  );
}
