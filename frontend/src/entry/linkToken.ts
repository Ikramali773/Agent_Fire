// Password-reset and invitation links arrive as `?reset=<token>` and
// `?invite=<token>` on the app's own origin (see the backend's _reset_url
// and _invite_url). There is no router in this app - navigation is the
// `activeView` state in App.tsx - so rather than adding one for two links,
// the query string is read once at startup and the matching full-screen
// step takes over the whole app until it is done.
export type LinkTokenKind = "reset" | "invite";

export interface LinkToken {
  kind: LinkTokenKind;
  token: string;
}

export function readLinkToken(search: string = window.location.search): LinkToken | null {
  const params = new URLSearchParams(search);
  for (const kind of ["reset", "invite"] as const) {
    const token = params.get(kind)?.trim();
    if (token) return { kind, token };
  }
  return null;
}

// Strips the token from the address bar once the step is finished. Matters
// for more than tidiness: the token is a credential, and leaving it in the
// URL leaves it in the history of a machine that may be shared, and in the
// Referer of anything the page links to afterwards.
export function clearLinkToken(): void {
  try {
    const url = new URL(window.location.href);
    url.searchParams.delete("reset");
    url.searchParams.delete("invite");
    window.history.replaceState({}, "", url.pathname + url.search + url.hash);
  } catch {
    // No History API (or an exotic embedding) - the step still completed,
    // and a stale query param is not worth failing over.
  }
}
