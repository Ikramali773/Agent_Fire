import { useState } from "react";
import { api } from "../api/client";
import { Button } from "../design-system/components/Button";
import { Modal } from "../design-system/components/Modal";
import { useAuth } from "./AuthContext";
import { authErrorMessage } from "./errors";
import "./LoginModal.css";

interface Props {
  onClose: () => void;
}

type Mode = "login" | "signup" | "forgot";

const TITLES: Record<Mode, string> = {
  login: "Sign in",
  signup: "Create account",
  forgot: "Reset your password",
};

export function LoginModal({ onClose }: Props) {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resetSent, setResetSent] = useState(false);

  const switchTo = (next: Mode) => {
    setMode(next);
    setError(null);
    setResetSent(false);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (mode === "login") {
        await login(email, password);
        onClose();
      } else if (mode === "signup") {
        await signup(email, password);
        onClose();
      } else {
        await api.requestPasswordReset(email);
        setResetSent(true);
      }
    } catch (err) {
      setError(authErrorMessage(err, "Something went wrong."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title={TITLES[mode]} onClose={onClose}>
      <form className="ds-login-modal" onSubmit={handleSubmit}>
        {mode === "forgot" ? (
          <p className="ds-login-modal__note">
            Enter the address on your account and we'll send a link to choose a new password. The link is good for one
            hour and can only be used once.
          </p>
        ) : (
          <p className="ds-login-modal__note">
            Signing in lets your case files belong to your account, so you can find them again later. You can keep using
            the app without an account too.
          </p>
        )}

        {/* Deliberately says "if there is an account", not "we sent it".
            The backend answers identically either way so this page cannot
            be used to find out who uses the product, and the wording has to
            keep that promise rather than quietly breaking it. */}
        {resetSent ? (
          <div className="ds-login-modal__sent" role="status">
            If there's an account for {email}, a reset link is on its way. Check your inbox, then come back and sign in
            with your new password.
          </div>
        ) : (
          <>
            <label className="ds-login-modal__field">
              <span>Email</span>
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
            </label>
            {mode !== "forgot" && (
              <label className="ds-login-modal__field">
                <span>Password</span>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
            )}
          </>
        )}

        {error && (
          <div className="ds-login-modal__error" role="alert">
            {error}
          </div>
        )}

        <div className="ds-login-modal__actions">
          {resetSent ? (
            <Button type="button" variant="primary" onClick={() => switchTo("login")}>
              Back to sign in
            </Button>
          ) : (
            <Button type="submit" variant="primary" disabled={loading}>
              {loading ? "Please wait…" : mode === "login" ? "Sign in" : mode === "signup" ? "Create account" : "Send reset link"}
            </Button>
          )}
          {!resetSent && (
            <button type="button" className="ds-login-modal__switch" onClick={() => switchTo(mode === "login" ? "signup" : "login")}>
              {mode === "login" ? "Need an account? Create one" : "Already have an account? Sign in"}
            </button>
          )}
        </div>

        {mode === "login" && !resetSent && (
          <button type="button" className="ds-login-modal__forgot" onClick={() => switchTo("forgot")}>
            Forgot your password?
          </button>
        )}
      </form>
    </Modal>
  );
}
