import { useCallback, useEffect, useState } from "react";

// Pins are per-user UI state, and the Case File schema is fixed - there is
// no field on it for "this person pinned this project", and inventing one
// would mean one account's preference riding on a shared record. So they
// live in this browser, namespaced by account so two people sharing a
// machine don't see each other's pins.
//
// The honest limitation: a pin does NOT follow the account to another
// browser or device. Making it do so needs a per-user preferences store,
// which does not exist yet - see frontend/README.md's "Not yet built".
const STORAGE_PREFIX = "fire-agent-pinned-chats";

function storageKey(userId: string | null): string {
  return `${STORAGE_PREFIX}:${userId ?? "anonymous"}`;
}

function read(userId: string | null): string[] {
  try {
    const raw = localStorage.getItem(storageKey(userId));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    // Anything could be under this key - another version of the app, or a
    // person editing it by hand. Take only what is actually usable.
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export interface PinnedChats {
  isPinned: (sessionId: string) => boolean;
  toggle: (sessionId: string) => void;
  count: number;
}

export function usePinnedChats(userId: string | null): PinnedChats {
  const [pinned, setPinned] = useState<string[]>(() => read(userId));

  // Signing in or out swaps which set of pins applies.
  useEffect(() => {
    setPinned(read(userId));
  }, [userId]);

  const toggle = useCallback(
    (sessionId: string) => {
      setPinned((current) => {
        const next = current.includes(sessionId)
          ? current.filter((item) => item !== sessionId)
          : [sessionId, ...current];
        try {
          localStorage.setItem(storageKey(userId), JSON.stringify(next));
        } catch {
          // Private browsing / storage disabled - the pin holds for this
          // session and is forgotten on reload, which beats throwing.
        }
        return next;
      });
    },
    [userId],
  );

  const isPinned = useCallback((sessionId: string) => pinned.includes(sessionId), [pinned]);

  return { isPinned, toggle, count: pinned.length };
}
