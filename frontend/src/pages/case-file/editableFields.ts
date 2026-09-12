// Coercion helpers for turning a DataRow's raw text edit back into the type
// the backend's Case File schema expects. The PUT /case-files/{id} endpoint
// re-validates through Pydantic (see backend/app/api/case_files.py), so a
// wrongly-typed value is safely rejected server-side rather than silently
// corrupting the case file - these just make the common cases (numbers,
// yes/no, comma lists) round-trip cleanly instead of always erroring.
export function parseNumberOrNull(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

export function parseBoolean(raw: string): boolean {
  return /^(true|yes|1)$/i.test(raw.trim());
}

export function parseStringList(raw: string): string[] {
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
