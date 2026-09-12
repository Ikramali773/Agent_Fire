import "./DisclaimerFooter.css";

// Persistent, unobtrusive - present on every screen, never removed or
// dismissed. This product gives advisory guidance, never a statutory
// approval; that distinction has to stay visible at all times.
export function DisclaimerFooter() {
  return (
    <footer className="ds-disclaimer-footer">
      Advisory only — not a statutory approval. Confirm with a licensed fire consultant before filing.
    </footer>
  );
}
