import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { EmptyState } from "../../design-system/components/EmptyState";
import { StatusPill } from "../../design-system/components/StatusPill";
import { relativeTime } from "../../lib/relativeTime";
import { reviewReasonLabel, reviewStatusLabel, reviewStatusTone } from "../../lib/review";
import type { ReviewQueueItem } from "../../types";
import "./ReviewQueue.css";

interface Props {
  selectedSessionId: string | null;
  onSelect: (item: ReviewQueueItem) => void;
  /** Bumped by the page after a verdict, so the queue reflects it. */
  refreshKey: number;
}

// The queue is OLDEST FIRST (the backend orders it that way), unlike every
// other list in this product. A chat rail is newest-first because you are
// resuming what you were just doing; a compliance queue is oldest-first
// because the case that has been waiting longest is the one most at risk of
// being forgotten.
export function ReviewQueue({ selectedSessionId, onSelect, refreshKey }: Props) {
  const [items, setItems] = useState<ReviewQueueItem[] | null>(null);
  const [includeSettled, setIncludeSettled] = useState(false);
  // Phase 4: a team's queue is everyone's queue, which is not much use to
  // the person who has to clear their own. Filtering is client-side
  // because the rows are already here - the backend sends assigned_to_me
  // per row - and a round trip to hide some of them would be waste.
  const [mineOnly, setMineOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let current = true;
    setError(null);
    api
      .myReviewQueue(includeSettled)
      .then((queue) => {
        if (current) setItems(queue);
      })
      .catch((err) => {
        if (current)
          setError(err instanceof ApiError ? `Could not load the queue (${err.status}).` : "Could not load the queue.");
      });
    return () => {
      current = false;
    };
  }, [includeSettled]);

  useEffect(load, [load, refreshKey]);

  const visible = items === null ? null : mineOnly ? items.filter((item) => item.assigned_to_me) : items;
  const assignedToMeCount = items?.filter((item) => item.assigned_to_me).length ?? 0;

  return (
    <div className="ds-review-queue">
      <header className="ds-review-queue__header">
        <h2 className="ds-review-queue__title">Queue</h2>
        <label className="ds-review-queue__toggle">
          <input
            type="checkbox"
            checked={includeSettled}
            onChange={(event) => setIncludeSettled(event.target.checked)}
          />
          Show settled
        </label>
      </header>

      {/* Only offered when something actually is assigned to you - a
          filter that can only ever empty the list is noise. */}
      {assignedToMeCount > 0 && (
        <label className="ds-review-queue__toggle ds-review-queue__toggle--filter">
          <input
            type="checkbox"
            checked={mineOnly}
            onChange={(event) => setMineOnly(event.target.checked)}
          />
          Only cases assigned to me ({assignedToMeCount})
        </label>
      )}

      {error && (
        <p className="ds-review-queue__note ds-review-queue__note--error" role="alert">
          {error}
        </p>
      )}

      {items === null && !error && <p className="ds-review-queue__note">Loading…</p>}

      {visible !== null && visible.length === 0 && (
        <EmptyState
          title={mineOnly ? "Nothing assigned to you" : "Nothing waiting"}
          description={
            mineOnly
              ? "Other cases are waiting, but none of them are yours. Untick the filter to see them."
              : includeSettled
                ? "No case has ever been flagged for review on this account."
                : "No flagged case is waiting. Settled ones are hidden — tick “Show settled” to see them."
          }
        />
      )}

      {visible !== null && visible.length > 0 && (
        <ul className="ds-review-queue__list">
          {visible.map((item) => (
            <li key={item.session_id}>
              <button
                type="button"
                className={`ds-review-queue__item${
                  item.session_id === selectedSessionId ? " ds-review-queue__item--active" : ""
                }`}
                onClick={() => onSelect(item)}
                aria-current={item.session_id === selectedSessionId ? "true" : undefined}
              >
                <span className="ds-review-queue__item-head">
                  <span className="ds-review-queue__item-name">{item.project_name || "Untitled project"}</span>
                  <StatusPill status={reviewStatusTone(item.status)} label={reviewStatusLabel(item.status)} size="sm" />
                  {/* Overdue is advisory - nothing acts when a due date
                      passes - so it is said plainly and never as a
                      compliance status, which this product does not issue. */}
                  {item.is_overdue && <StatusPill status="fail" label="Overdue" size="sm" />}
                </span>
                <span className="ds-review-queue__item-reasons">
                  {item.reason_codes.map(reviewReasonLabel).join(" · ") || "No reason recorded"}
                </span>
                <span className="ds-review-queue__item-meta">
                  {/* Whose project this is matters: a reviewer looking at
                      someone else's case cannot change its facts. */}
                  {item.is_owner ? "Your project" : "Shared with you"} · waiting since{" "}
                  {relativeTime(item.updated_at)}
                </span>
                {item.assignment?.assigned_to_email && (
                  <span className="ds-review-queue__item-meta">
                    {item.assigned_to_me ? "Assigned to you" : `Assigned to ${item.assignment.assigned_to_email}`}
                    {item.assignment.due_at && ` · due ${relativeTime(item.assignment.due_at)}`}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
