import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ProjectSearchHit } from "../types";

// Long enough that a person has stopped typing a word, short enough not to
// feel laggy. Every keystroke hitting the server would be a query per
// character for no benefit - the local title match already answers
// instantly while this settles.
const DEBOUNCE_MS = 250;

// Below this the server refuses anyway (every project would match), so do
// not bother asking.
const MIN_QUERY_LENGTH = 2;

/**
 * Projects whose CONVERSATION mentions the query.
 *
 * Separate from the rail's own title filter on purpose: that one is
 * instant and local, this one is a round trip. Showing them together
 * would mean the whole list waited on the network to render results it
 * already had.
 *
 * `exclude` drops the ones the title match already found, so a project
 * does not appear twice under two headings.
 */
export function useConversationSearch(query: string, exclude: Set<string>): ProjectSearchHit[] {
  const [hits, setHits] = useState<ProjectSearchHit[]>([]);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setHits([]);
      return;
    }

    let cancelled = false;
    const timer = setTimeout(() => {
      void api
        .searchProjects(trimmed)
        .then((found) => {
          if (!cancelled) setHits(found.filter((hit) => hit.matched_in === "conversation"));
        })
        .catch(() => {
          // Signed out, offline, or the request failed. The local title
          // match still works, so show nothing extra rather than an error
          // in a sidebar.
          if (!cancelled) setHits([]);
        });
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  return hits.filter((hit) => !exclude.has(hit.session_id));
}
