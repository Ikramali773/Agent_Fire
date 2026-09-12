import { useState } from "react";
import { ApiError } from "../api/client";
import { Button } from "../design-system/components/Button";
import { Modal } from "../design-system/components/Modal";
import { useAuth } from "./AuthContext";
import "./LoginModal.css";

interface Props {
  onClose: () => void;
}

export function LoginModal({ onClose }: Props) {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await signup(email, password);
      }
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message.replace(/^\d+ [^:]+:\s*/, "") : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title={mode === "login" ? "Sign in" : "Create account"} onClose={onClose}>
      <form className="ds-login-modal" onSubmit={handleSubmit}>
        <p className="ds-login-modal__note">
          Signing in lets your case files belong to your account, so you can find them again later. You can keep using the app
          without an account too.
        </p>
        <label className="ds-login-modal__field">
          <span>Email</span>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        </label>
        <label className="ds-login-modal__field">
          <span>Password</span>
          <input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && (
          <div className="ds-login-modal__error" role="alert">
            {error}
          </div>
        )}
        <div className="ds-login-modal__actions">
          <Button type="submit" variant="primary" disabled={loading}>
            {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </Button>
          <button
            type="button"
            className="ds-login-modal__switch"
            onClick={() => {
              setMode(mode === "login" ? "signup" : "login");
              setError(null);
            }}
          >
            {mode === "login" ? "Need an account? Create one" : "Already have an account? Sign in"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
