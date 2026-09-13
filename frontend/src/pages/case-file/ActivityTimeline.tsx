import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { Button } from "../../design-system/components/Button";
import { parseApiTimestamp, relativeTime } from "../../lib/relativeTime";
import { changeFieldLabel, changeSourceLabel, describeChangeValue, groupChanges } from "../../lib/changeLog";
import type { FieldChange } from "../../types";
import "./ActivityTimeline.css";

const PAGE_SIZE = 25;

interface Props {
  sessionId: string;
  /** Bumped by the page after a save, to pull in the change it just made. */
  refreshKey: number;
}

// The per-field history of one case file - "this building was 24 m
// yesterday and 68 m today; who changed it, and off the back of what?".
// Project History is a project LIST showing current state only, so until
// this existed nothing in the product could answer that.
export function ActivityTimeline({ sessionId, refreshKey }: Props) {
  const [changes, setChanges] = useState<FieldChange[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [exhausted, setExhausted] = useState(false);

  useEffect(() => {
    let current = true;
    setError(null);
    api
      .getChanges(sessionId, { limit: PAGE_SIZE })
      .then((page) => {
        if (!current) return;
        setChanges(page);
        setExhausted(page.length < PAGE_SIZE);
      })
      .catch((err) => {
        if (!current) return;
        setError(err instanceof ApiError ? `Could not load the history (${err.status}).` : "Could not load the history.");
      });
    return () => {
      current = false;
    };
  }, [sessionId, refreshKey]);

  const loadMore = useCallback(async () => {
    if (!changes || changes.length === 0) return;
    setLoadingMore(true);
    setError(null);
    try {
      const page = await api.getChanges(sessionId, { limit: PAGE_SIZE, beforeId: changes[changes.length - 1].id });
      setChanges([...changes, ...page]);
      setExhausted(page.length < PAGE_SIZE);
    } catch (err) {
      setError(err instanceof ApiError ? `Could not load more history (${err.status}).` : "Could not load more history.");
    } finally {
      setLoadingMore(false);
    }
  }, [changes, sessionId]);

  if (error) {
    return (
      <p className="ds-activity__note ds-activity__note--error" role="alert">
        {error}
      </p>
    );
  }

  if (changes === null) return <p className="ds-activity__note">Loading history…</p>;

  if (changes.length === 0) {
    return <p className="ds-activity__note">Nothing has changed yet. Every edit, extracted fact and stage change shows up here.</p>;
  }

  return (
    <div className="ds-activity">
      <ol className="ds-activity__list">
        {groupChanges(changes).map((group) => (
          <li key={group.id} className="ds-activity__event">
            <div className="ds-activity__event-head">
              <span className="ds-activity__source">{changeSourceLabel(group.source)}</span>
              <time className="ds-activity__time" dateTime={group.createdAt} title={parseApiTimestamp(group.createdAt).toLocaleString()}>
                {relativeTime(group.createdAt)}
              </time>
            </div>
            <ul className="ds-activity__fields">
              {group.changes.map((change) => (
                <li key={change.id} className="ds-activity__field">
                  <span className="ds-activity__field-name">{changeFieldLabel(change.field)}</span>
                  <span className="ds-activity__from">{describeChangeValue(change.old_value)}</span>
                  <span className="ds-activity__arrow" aria-hidden="true">
                    →
                  </span>
                  <span className="ds-activity__to">{describeChangeValue(change.new_value)}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
      {!exhausted && (
        <Button variant="ghost" size="sm" onClick={() => void loadMore()} disabled={loadingMore}>
          {loadingMore ? "Loading…" : "Show earlier changes"}
        </Button>
      )}
    </div>
  );
}
