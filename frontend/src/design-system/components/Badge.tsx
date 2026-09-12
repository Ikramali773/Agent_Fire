import "./Badge.css";

type Tone = "neutral" | "accent" | "phase";

interface Props {
  children: React.ReactNode;
  tone?: Tone;
}

// Generic small tag - code-edition badges, "Phase 2" markers, counts.
// Distinct from StatusPill (which always carries compliance/status meaning)
// and SourceBadge (which always carries provenance meaning).
export function Badge({ children, tone = "neutral" }: Props) {
  return <span className={`ds-badge ds-badge--${tone}`}>{children}</span>;
}
