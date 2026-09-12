// Buckets, largest unit first. Intl.RelativeTimeFormat does the wording
// (and the localisation); this only decides which unit to use.
const UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["year", 365 * 24 * 60 * 60 * 1000],
  ["month", 30 * 24 * 60 * 60 * 1000],
  ["week", 7 * 24 * 60 * 60 * 1000],
  ["day", 24 * 60 * 60 * 1000],
  ["hour", 60 * 60 * 1000],
  ["minute", 60 * 1000],
];

const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

/** "2 hours ago", "yesterday", "just now" - for chat-history timestamps. */
export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const elapsed = then - Date.now();
  const magnitude = Math.abs(elapsed);
  for (const [unit, ms] of UNITS) {
    if (magnitude >= ms) return formatter.format(Math.round(elapsed / ms), unit);
  }
  return "just now";
}
