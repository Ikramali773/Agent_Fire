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
  Users,
  type LucideIcon,
} from "lucide-react";

// Every "page" the shell can route to. Phase 1 activated overview,
// case-file, documents, compliance and reports; Phase 2 added history and
// Phase 3 added review. What is left (see NAV_ITEMS' `comingInPhase`) are
// real, permanent nav entries not yet wired to working screens. Never fake
// a future page as functional.
export type ViewKey =
  | "overview"
  | "case-file"
  | "documents"
  | "compliance"
  | "plans"
  | "findings"
  | "reports"
  | "review"
  | "team"
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
  { key: "findings", label: "Findings", icon: Search },
  { key: "reports", label: "Reports", icon: ClipboardList },
  { key: "review", label: "Review", icon: ClipboardCheck },
  { key: "team", label: "Team", icon: Users },
  { key: "history", label: "Project History", icon: History },
];

export const VIEW_LABELS: Record<ViewKey, string> = Object.fromEntries(
  NAV_ITEMS.map((item) => [item.key, item.label]),
) as Record<ViewKey, string>;
