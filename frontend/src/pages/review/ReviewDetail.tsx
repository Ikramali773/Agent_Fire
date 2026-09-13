import { Download, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { Button } from "../../design-system/components/Button";
import { Card } from "../../design-system/components/Card";
import { StatusPill } from "../../design-system/components/StatusPill";
import { parseApiTimestamp, relativeTime } from "../../lib/relativeTime";
import { RECORDABLE_STATUSES, reviewReasonLabel, reviewStatusLabel, reviewStatusTone } from "../../lib/review";
import { SharePanel } from "./SharePanel";
import type { ReviewState, ReviewStatus } from "../../types";
import "./ReviewDetail.css";

interface Props {
  sessionId: string;
  /** Whether to offer sharing. False for a reviewer (who must not pass the
   *  project onward) and for an anonymous session (no account to share
   *  as - the server answers 401). */
  canShare: boolean;
  /** Called after a verdict, so the queue behind this reflects it. */
  onRecorded: () => void;
}

function triggerBrowserDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function ReviewDetail({ sessionId, canShare, onRecorded }: Props) {
  const [state, setState] = useState<ReviewState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<ReviewStatus>("in_review");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState<"pdf" | "docx" | null>(null);

  useEffect(() => {
    let current = true;
    setState(null);
    setError(null);
    setNote("");
    api
      .getReview(sessionId)
      .then((next) => {
        if (current) setState(next);
      })
      .catch((err) => {
        if (current)
          setError(err instanceof ApiError ? `Could not load this review (${err.status}).` : "Could not load this review.");
      });
    return () => {
      current = false;
    };
  }, [sessionId]);

  const record = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      setState(await api.recordReview(sessionId, verdict, note.trim()));
      setNote("");
      onRecorded();
    } catch (err) {
      setError(
        err instanceof ApiError ? `Could not record that verdict (${err.status}).` : "Could not record that verdict.",
      );
    } finally {
      setSaving(false);
    }
  }, [note, onRecorded, sessionId, verdict]);

  const download = async (format: "pdf" | "docx") => {
    setDownloading(format);
    setError(null);
    try {
      const { blob, filename } = await api.downloadHandoff(sessionId, format);
      triggerBrowserDownload(blob, filename);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? `Could not download the handoff pack (${err.status}).`
          : "Could not download the handoff pack.",
      );
    } finally {
      setDownloading(null);
    }
  };

  if (error && state === null) {
    return (
      <p className="ds-review-detail__note ds-review-detail__note--error" role="alert">
        {error}
      </p>
    );
  }
  if (state === null) return <p className="ds-review-detail__note">Loading…</p>;

  return (
    <div className="ds-review-detail">
      <header className="ds-review-detail__header">
        <div>
          <h2>{state.project_name || "Untitled project"}</h2>
          <p className="ds-review-detail__sub">
            Waiting since {relativeTime(state.flagged_at ?? new Date().toISOString())}
          </p>
        </div>
        <StatusPill status={reviewStatusTone(state.status)} label={reviewStatusLabel(state.status)} />
      </header>

      {error && (
        <div className="ds-review-detail__error" role="alert">
          {error}
        </div>
      )}

      <Card title="Why this needs a person">
        {state.requires_review ? (
          <>
            <p className="ds-review-detail__lead">
              The deterministic engine flagged this case. Each item is a specific reason it could not finish, not a
              general caveat.
            </p>
            <ul className="ds-review-detail__reasons">
              {state.reasons.map((reason, index) => (
                <li key={`${reason.code}-${index}`}>
                  <span className="ds-review-detail__reason-code">{reviewReasonLabel(reason.code)}</span>
                  <span className="ds-review-detail__reason-detail">{reason.detail}</span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="ds-review-detail__lead">
            The engine did <strong>not</strong> flag this case. You are reviewing it by choice, which is fine — the
            verdict is recorded either way.
          </p>
        )}
      </Card>

      <Card title="Handoff pack">
        <p className="ds-review-detail__lead">
          The report, plus why review is required, where every fact came from (user-confirmed, extracted from a drawing
          at what confidence, or inferred), and what has changed since. This is what a licensed consultant needs in
          order to sign off on someone else's numbers.
        </p>
        <div className="ds-review-detail__actions">
          <Button
            variant="secondary"
            size="sm"
            icon={downloading === "pdf" ? <Loader2 className="ds-review-detail__spin" /> : <Download />}
            disabled={downloading !== null}
            onClick={() => void download("pdf")}
          >
            Download PDF
          </Button>
          <Button
            variant="secondary"
            size="sm"
            icon={downloading === "docx" ? <Loader2 className="ds-review-detail__spin" /> : <Download />}
            disabled={downloading !== null}
            onClick={() => void download("docx")}
          >
            Download DOCX
          </Button>
        </div>
      </Card>

      {state.can_record_verdict && (
        <Card title="Record a verdict">
          <p className="ds-review-detail__lead">
            Your verdict is recorded <em>alongside</em> the classification and never replaces it. If you think the
            answer is wrong, change the facts on the Case File page and let the engine reclassify.
          </p>
          <div className="ds-review-detail__form">
            <label className="ds-review-detail__label" htmlFor="ds-review-verdict">
              Verdict
            </label>
            <select
              id="ds-review-verdict"
              className="ds-review-detail__select"
              value={verdict}
              onChange={(event) => setVerdict(event.target.value as ReviewStatus)}
              disabled={saving}
            >
              {RECORDABLE_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {reviewStatusLabel(status)}
                </option>
              ))}
            </select>

            <label className="ds-review-detail__label" htmlFor="ds-review-note">
              Note
            </label>
            <textarea
              id="ds-review-note"
              className="ds-review-detail__textarea"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="What did you check, and what did you conclude?"
              rows={3}
              disabled={saving}
            />

            <div className="ds-review-detail__actions">
              <Button variant="primary" size="sm" onClick={() => void record()} disabled={saving}>
                {saving ? "Recording…" : "Record verdict"}
              </Button>
            </div>
          </div>
        </Card>
      )}

      <Card title="Review history">
        {state.events.length === 0 ? (
          <p className="ds-review-detail__lead">Nothing recorded yet.</p>
        ) : (
          <ol className="ds-review-detail__events">
            {state.events.map((event) => (
              <li key={event.id} className="ds-review-detail__event">
                <div className="ds-review-detail__event-head">
                  <StatusPill status={reviewStatusTone(event.status)} label={reviewStatusLabel(event.status)} size="sm" />
                  <span className="ds-review-detail__event-who">{event.actor_email ?? "Anonymous session"}</span>
                  <time dateTime={event.created_at} title={parseApiTimestamp(event.created_at).toLocaleString()}>
                    {relativeTime(event.created_at)}
                  </time>
                </div>
                {event.note && <p className="ds-review-detail__event-note">{event.note}</p>}
              </li>
            ))}
          </ol>
        )}
      </Card>

      {/* Sharing is owner-only: a reviewer must never be able to pass
          someone else's project onward, and an anonymous session has no
          account to share as. The backend enforces both. */}
      {canShare && <SharePanel sessionId={sessionId} />}
    </div>
  );
}
