import { CheckCircle2, CircleHelp, OctagonX, ShieldAlert, TriangleAlert } from "lucide-react";
import "./StatusPill.css";

// The one status vocabulary used everywhere in the product — case file
// fields, compliance requirements, documents, and (from Phase 4 on) plan
// findings and the review queue all render through this same component so
// "what does this status mean" never has to be relearned per screen.
export type Status = "pass" | "fail" | "warning" | "unknown" | "human_review" | "info";

const STATUS_META: Record<Status, { label: string; Icon: typeof CheckCircle2 }> = {
  pass: { label: "Pass", Icon: CheckCircle2 },
  fail: { label: "Fail", Icon: OctagonX },
  warning: { label: "Warning", Icon: TriangleAlert },
  unknown: { label: "Unknown", Icon: CircleHelp },
  human_review: { label: "Human review", Icon: ShieldAlert },
  info: { label: "Info", Icon: CircleHelp },
};

interface Props {
  status: Status;
  label?: string;
  size?: "sm" | "md";
}

// Status is communicated by icon + text together, never color alone (a
// standing accessibility requirement for a compliance product where
// getting a status wrong has real consequences).
export function StatusPill({ status, label, size = "md" }: Props) {
  const meta = STATUS_META[status];
  const Icon = meta.Icon;
  return (
    <span className={`ds-status-pill ds-status-pill--${status} ds-status-pill--${size}`}>
      <Icon aria-hidden="true" />
      {label ?? meta.label}
    </span>
  );
}
