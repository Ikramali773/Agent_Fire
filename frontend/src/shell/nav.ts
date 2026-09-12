import {
  LayoutDashboard,
  FileText,
  FolderOpen,
  ShieldCheck,
  Map,
  Search,
  ClipboardList,
  ClipboardCheck,
  History,
  type LucideIcon,
} from "lucide-react";

// Every "page" the shell can route to. Phase 1 activates only overview,
// case-file, documents, compliance and reports (see NAV_ITEMS' `phase`
// field) - the rest are real, permanent nav entries, just not wired to
// working screens yet. Never fake a future page as functional.
export type ViewKey =
  | "overview"
  | "case-file"
  | "documents"
  | "compliance"
  | "plans"
  | "findings"
  | "reports"
  | "review"
  | "history";

export interface NavItem {
  key: ViewKey;
  label: string;
  icon: LucideIcon;
  /** Set only for items not active in Phase 1 - the phase that introduces them. */
  comingInPhase?: number;
}

export const NAV_ITEMS: NavItem[] = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "case-file", label: "Case File", icon: FileText },
  { key: "documents", label: "Documents", icon: FolderOpen },
  { key: "compliance", label: "Compliance", icon: ShieldCheck },
  { key: "plans", label: "Plans", icon: Map, comingInPhase: 4 },
  { key: "findings", label: "Findings", icon: Search, comingInPhase: 4 },
  { key: "reports", label: "Reports", icon: ClipboardList },
  { key: "review", label: "Review", icon: ClipboardCheck, comingInPhase: 3 },
  { key: "history", label: "Project History", icon: History, comingInPhase: 2 },
];

export const VIEW_LABELS: Record<ViewKey, string> = Object.fromEntries(
  NAV_ITEMS.map((item) => [item.key, item.label]),
) as Record<ViewKey, string>;
