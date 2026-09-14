import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";

// Where a signed-out person's pins go. There is no account to attach them
// to, so the browser is the only honest place for them - and the same key
// is what a newly signed-in account's pins are migrated FROM, once.
//
// Namespaced by account id even so, because two people sharing a machine
// must not see each other's pins while signed out.
const STORAGE_PREFIX = "fire-agent-pinned-chats";

function storageKey(userId: string | null): string {
  return `${STORAGE_PREFIX}:${userId ?? "anonymous"}`;
}

function readLocal(userId: string | null): string[] {
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

function writeLocal(userId: string | null, pinned: string[]): void {
  try {
    localStorage.setItem(storageKey(userId), JSON.stringify(pinned));
  } catch {
    // Private browsing / storage disabled - the pin holds for this session
    // and is forgotten on reload, which beats throwing.
  }
}

function clearLocal(userId: string | null): void {
  try {
    localStorage.removeItem(storageKey(userId));
  } catch {
    /* ignore */
  }
}

export interface PinnedChats {
  isPinned: (sessionId: string) => boolean;
  toggle: (sessionId: string) => void;
  count: number;
}

/**
 * Pinned projects for whoever is signed in.
 *
 * Signed in, pins live on the account (`/users/me/preferences`), so they
 * follow the person to another browser or a phone. Signed out there is no
 * account to attach them to, so they stay in this browser.
 *
 * Writes are optimistic: the pin flips immediately and the request goes
 * out behind it. Pinning is a UI convenience, and making someone wait on a
 * round trip to see a star fill in would be worse than the rare case of a
 * failed write being reconciled on the next load.
 */
export function usePinnedChats(userId: string | null): PinnedChats {
  const [pinned, setPinned] = useState<string[]>(() => readLocal(userId));
  // Which account's pins `pinned` currently holds. Guards against a slow
  // response for the previous account landing after a switch and
  // overwriting the new one's - a real hazard when signing out and back in
  // as someone else on a shared machine.
  const loadedFor = useRef<string | null>(userId);

  useEffect(() => {
    loadedFor.current = userId;
    if (!userId) {
      setPinned(readLocal(null));
      return;
    }

    let cancelled = false;
    void (async () => {
      try {
        const stored = await api.getPreferences();
        if (cancelled || loadedFor.current !== userId) return;

        // Pins made in this browser before the account had anywhere to put
        // them. Merged rather than dropped: someone who pinned ten projects
        // and then signed up should not silently lose them. Once merged the
        // local copy goes, so this happens exactly once per browser.
        const local = readLocal(userId);
        const orphans = local.filter((id) => !stored.pinned_session_ids.includes(id));
        if (orphans.length === 0) {
          setPinned(stored.pinned_session_ids);
          clearLocal(userId);
          return;
        }
        const merged = [...orphans, ...stored.pinned_session_ids];
        setPinned(merged);
        const saved = await api.savePreferences({ pinned_session_ids: merged });
        if (cancelled || loadedFor.current !== userId) return;
        setPinned(saved.pinned_session_ids);
        clearLocal(userId);
      } catch {
        // Offline, or the request failed. Fall back to whatever this
        // browser knows rather than showing no pins at all - and do NOT
        // clear the local copy, which is now the only one there is.
        if (!cancelled && loadedFor.current === userId) setPinned(readLocal(userId));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [userId]);

  const toggle = useCallback(
    (sessionId: string) => {
      setPinned((current) => {
        const next = current.includes(sessionId)
          ? current.filter((item) => item !== sessionId)
          : [sessionId, ...current];
        if (userId) {
          void api.savePreferences({ pinned_session_ids: next }).catch(() => {
            // The pin stays flipped for this session. Reconciled on the
            // next load rather than yanked back under the cursor.
          });
        } else {
          writeLocal(null, next);
        }
        return next;
      });
    },
    [userId],
  );

  const isPinned = useCallback((sessionId: string) => pinned.includes(sessionId), [pinned]);

  return { isPinned, toggle, count: pinned.length };
}
