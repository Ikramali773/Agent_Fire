import { useState } from "react";
import { Button } from "../design-system/components/Button";
import { Modal } from "../design-system/components/Modal";
import { useAuth } from "./AuthContext";
import { authErrorMessage } from "./errors";
import { MIN_PASSWORD_LENGTH } from "./password";
import "./LoginModal.css";

interface Props {
  onClose: () => void;
}

export function ChangePasswordModal({ onClose }: Props) {
  const { changePassword } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    // Checked here as well as by the server: a typo in the confirmation
    // would otherwise change the password to something nobody knows.
    if (newPassword !== confirmPassword) {
      setError("The two new passwords don't match.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await changePassword(currentPassword, newPassword);
      onClose();
    } catch (err) {
      setError(authErrorMessage(err, "Could not change your password."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="Change password" onClose={onClose}>
      <form className="ds-login-modal" onSubmit={handleSubmit}>
        <p className="ds-login-modal__note">
          You'll stay signed in here. Every other device signed in to this account will be signed out — which is the
          point if you're changing it because the old one may have been seen.
        </p>
        <label className="ds-login-modal__field">
          <span>Current password</span>
          <input
            type="password"
            required
            autoFocus
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
        </label>
        <label className="ds-login-modal__field">
          <span>New password</span>
          <input
            type="password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
        </label>
        <label className="ds-login-modal__field">
          <span>Confirm new password</span>
          <input
            type="password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
        </label>
        {error && (
          <div className="ds-login-modal__error" role="alert">
            {error}
          </div>
        )}
        <div className="ds-login-modal__actions">
          <Button type="submit" variant="primary" disabled={loading}>
            {loading ? "Changing…" : "Change password"}
          </Button>
          <button type="button" className="ds-login-modal__switch" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Modal>
  );
}
