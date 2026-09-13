import type { CaseFile, User } from "../types";

/**
 * Whether this user may CHANGE a case file, as opposed to only read it.
 *
 * Mirrors the backend's `Access.WRITE` (see api/case_files.py::_check_access)
 * so the UI never offers an action the server will refuse:
 *
 * - an anonymous case file has no owner, and is open to anyone holding its
 *   session id - Phase 1's original model, unchanged;
 * - an owned case file is writable only by its owner. A reviewer it was
 *   shared with gets read access and the ability to record a verdict, and
 *   nothing else.
 *
 * This is a mirror, not the enforcement. The server decides; this only
 * stops the UI from inviting someone into a 403.
 */
export function canEditCaseFile(caseFile: CaseFile | null, user: User | null): boolean {
  if (!caseFile) return true;
  if (caseFile.owner_user_id === null) return true;
  return user !== null && user.id === caseFile.owner_user_id;
}

/** True when the user can see this case file but not change it. */
export function isReadOnlyCaseFile(caseFile: CaseFile | null, user: User | null): boolean {
  return caseFile !== null && !canEditCaseFile(caseFile, user);
}
