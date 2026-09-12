import type { LucideIcon } from "lucide-react";
import { Badge } from "../design-system/components/Badge";
import { EmptyState } from "../design-system/components/EmptyState";
import "./ComingSoonPage.css";

interface Props {
  icon: LucideIcon;
  title: string;
  phase: number;
  description: string;
}

// Real, permanent nav destinations for work this product will do later
// (Plans/Findings in Phase 4, Review in Phase 3, Project History in
// Phase 2) - never faked as functional, always clearly labelled with the
// phase that introduces them. The Sidebar already prevents navigating
// here directly; this is the honest landing spot if that ever changes.
export function ComingSoonPage({ icon: Icon, title, phase, description }: Props) {
  return (
    <div className="ds-coming-soon">
      <EmptyState icon={<Icon />} title={title} description={description} action={<Badge tone="phase">Coming in Phase {phase}</Badge>} />
    </div>
  );
}
