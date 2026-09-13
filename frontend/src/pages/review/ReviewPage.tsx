import { useState } from "react";
import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { LoginModal } from "../../auth/LoginModal";
import { Button } from "../../design-system/components/Button";
import { EmptyState } from "../../design-system/components/EmptyState";
import { ReviewDetail } from "./ReviewDetail";
import { ReviewQueue } from "./ReviewQueue";
import type { CaseFile, ReviewQueueItem } from "../../types";
import "./ReviewPage.css";

// Phase 3. The classifier has always been able to say "a person has to
// look at this" - in 15 different situations - and until this page that
// flag was a dead end: nothing listed flagged cases, tracked whether
// anyone looked, or recorded what they concluded.
//
// Master-detail rather than a table: acting on a case needs the reasons,
// the handoff pack and the verdict form together, and bouncing between a
// list page and a detail page for each one is how a queue stops getting
// worked.
interface Props {
  /** The open project, so a signed-out user can still review it. */
  caseFile: CaseFile | null;
  /** Makes the selected case the active project, so the header, breadcrumb
   *  and Case File inspector follow what is on screen. */
  onCaseFileChange: (caseFile: CaseFile) => void;
}

export function ReviewPage({ caseFile, onCaseFileChange }: Props) {
  const { user } = useAuth();
  const [selected, setSelected] = useState<ReviewQueueItem | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  // Bumped after a verdict so the queue re-reads (a settled case leaves it).
  const [refreshKey, setRefreshKey] = useState(0);

  // Signed out there is no queue - a queue spans projects, and an
  // anonymous session has exactly one. But the open project can still be
  // reviewed: the backend treats an anonymous case file as open to whoever
  // holds its session id, verdicts included. Sending someone here from the
  // "a person has to look at this" banner and then showing them a sign-in
  // wall would be a dead end of our own making.
  if (!user) {
    return (
      <div className="ds-review-page">
        <header className="ds-review-page__header">
          <h1>Review</h1>
          <p>
            Sign in to get a queue across all your projects, and to hand a case to a consultant for review. Without an
            account you can still review the project you have open.
          </p>
        </header>
        {caseFile ? (
          <>
            <div className="ds-review-page__signin-prompt">
              <Button variant="secondary" size="sm" onClick={() => setLoginOpen(true)}>
                Sign in
              </Button>
            </div>
            <ReviewDetail key={caseFile.session_id} sessionId={caseFile.session_id} canShare={false} onRecorded={() => undefined} />
          </>
        ) : (
          <EmptyState
            title="No project open"
            description="Start a project on the Overview page, or sign in to see every case waiting for review across your projects."
            action={
              <Button variant="primary" size="sm" onClick={() => setLoginOpen(true)}>
                Sign in
              </Button>
            }
          />
        )}
        {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
      </div>
    );
  }

  return (
    <div className="ds-review-page">
      <header className="ds-review-page__header">
        <h1>Review</h1>
        <p>
          Cases the deterministic engine could not finish on its own, oldest first — the one waiting longest is the one
          most likely to be forgotten. A verdict here is recorded alongside the classification and never replaces it.
        </p>
      </header>

      <div className="ds-review-page__body">
        <div className="ds-review-page__queue">
          <ReviewQueue
            selectedSessionId={selected?.session_id ?? null}
            onSelect={(item) => {
              setSelected(item);
              // Otherwise the shell header keeps saying "Untitled project"
              // and the inspector "No active case yet" while the page
              // itself shows a named project - the reader has to decide
              // which one to believe.
              void api.getCaseFile(item.session_id).then(onCaseFileChange).catch(() => undefined);
            }}
            refreshKey={refreshKey}
          />
        </div>
        <div className="ds-review-page__detail">
          {selected ? (
            <ReviewDetail
              key={selected.session_id}
              sessionId={selected.session_id}
              canShare={selected.is_owner}
              onRecorded={() => setRefreshKey((key) => key + 1)}
            />
          ) : (
            <EmptyState
              title="Pick a case"
              description="Choose a case from the queue to see why it was flagged, download the handoff pack for a consultant, and record a verdict."
            />
          )}
        </div>
      </div>
    </div>
  );
}
