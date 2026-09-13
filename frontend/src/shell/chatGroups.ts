import { parseApiTimestamp } from "../lib/relativeTime";
import type { CaseFile } from "../types";

export interface ChatGroup {
  key: string;
  label: string;
  projects: CaseFile[];
}

const DAY_MS = 24 * 60 * 60 * 1000;

// Calendar days apart, not elapsed hours: something touched at 11pm was
// "yesterday" by 1am, even though barely two hours have passed.
function daysAgo(iso: string, now: Date): number {
  const then = parseApiTimestamp(iso);
  const thenMidnight = new Date(then.getFullYear(), then.getMonth(), then.getDate()).getTime();
  const nowMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  return Math.round((nowMidnight - thenMidnight) / DAY_MS);
}

function bucketFor(project: CaseFile, now: Date): { key: string; label: string } {
  const days = daysAgo(project.updated_at, now);
  if (days <= 0) return { key: "today", label: "Today" };
  if (days === 1) return { key: "yesterday", label: "Yesterday" };
  if (days <= 7) return { key: "week", label: "Previous 7 days" };
  if (days <= 30) return { key: "month", label: "Previous 30 days" };
  return { key: "older", label: "Older" };
}

/**
 * Splits projects into the date buckets a chat rail uses.
 *
 * Input is assumed newest-first (ProjectsContext keeps it that way), so
 * buckets come out in order without re-sorting. Empty buckets are dropped
 * rather than rendered as bare headings.
 */
export function groupChatsByRecency(projects: CaseFile[], now: Date = new Date()): ChatGroup[] {
  const groups: ChatGroup[] = [];
  for (const project of projects) {
    const { key, label } = bucketFor(project, now);
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.projects.push(project);
    else groups.push({ key, label, projects: [project] });
  }
  return groups;
}
