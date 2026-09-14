import { useState } from "react";
import { api } from "../api/client";
import { authErrorMessage } from "../auth/errors";
import { MIN_PASSWORD_LENGTH } from "../auth/password";
import { Button } from "../design-system/components/Button";
import "../auth/LoginModal.css";
import "./LinkScreen.css";

interface Props {
  // Finished with this link - go back to the ordinary app.
  onDone: () => void;
}

interface WithToken extends Props {
  token: string;
}

// The full-screen step behind a `?reset=<token>` link. Takes over the whole
// app rather than opening as a modal: whoever followed this link cannot get
// into their account, so there is nothing else for them to do here, and a
// dismissable dialog over a workspace they can't use would only confuse.
export function ResetPasswordScreen({ token, onDone }: WithToken) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (password !== confirm) {
      setError("The two passwords don't match.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.confirmPasswordReset(token, password);
      setDone(true);
    } catch (err) {
      // The backend's own sentence here is the useful one ("invalid,
      // already used, or expired"), and it is the difference between
      // "try again" and "ask for a new link".
      setError(authErrorMessage(err, "Could not reset your password."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ds-link-screen">
      <div className="ds-link-screen__card">
        <h1 className="ds-link-screen__title">{done ? "Password changed" : "Choose a new password"}</h1>

        {done ? (
          <>
            {/* No automatic sign-in: this endpoint answers 204 and never
                says whose account it was, deliberately, so there is no
                session to hand back here. */}
            <p className="ds-link-screen__lead">
              Your password has been changed and every device that was signed in to this account has been signed out.
              Sign in again with the new password.
            </p>
            <Button variant="primary" onClick={onDone}>
              Go to sign in
            </Button>
          </>
        ) : (
          <form className="ds-login-modal" onSubmit={submit}>
            <p className="ds-link-screen__lead">
              Pick a new password for your account. This link works once, and every device currently signed in will be
              signed out.
            </p>
            <label className="ds-login-modal__field">
              <span>New password</span>
              <input
                type="password"
                required
                autoFocus
                minLength={MIN_PASSWORD_LENGTH}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <label className="ds-login-modal__field">
              <span>Confirm new password</span>
              <input
                type="password"
                required
                minLength={MIN_PASSWORD_LENGTH}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </label>
            {error && (
              <div className="ds-login-modal__error" role="alert">
                {error}
              </div>
            )}
            <div className="ds-login-modal__actions">
              <Button type="submit" variant="primary" disabled={loading}>
                {loading ? "Saving…" : "Set new password"}
              </Button>
              <button type="button" className="ds-login-modal__switch" onClick={onDone}>
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
