// Detects when an agent message already enumerates its own answer options
// as a "/"-separated list (the dialogue nodes phrase questions this way,
// e.g. "Residential / Educational / Institutional (e.g. hospital) / ...").
// This never invents options - it only turns options the backend already
// wrote out in plain text into clickable chips instead of forcing retyping.
export function parseQuickOptions(text: string): string[] | null {
  const questionIndex = text.lastIndexOf("?");
  const tail = questionIndex >= 0 ? text.slice(questionIndex + 1) : text;
  if (!tail.includes("/")) return null;

  const candidates = tail
    .split("/")
    .map((option) => option.trim())
    .filter(Boolean);

  if (candidates.length < 2 || candidates.length > 12) return null;
  if (candidates.some((option) => option.length > 48)) return null;

  return candidates.map((option) => option.replace(/\s*\([^)]*\)\s*$/, "").trim());
}
