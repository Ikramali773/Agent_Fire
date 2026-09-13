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

// An ISO string with no offset ("2026-09-13T07:13:16") is parsed by the
// browser as LOCAL time. Every timestamp this API returns is UTC, so a row
// written before the backend started emitting an offset would otherwise
// read as hours out for anyone not in UTC - "just now" showing as "5 hours
// ago". Labelling those as UTC is a correction, not a guess.
const HAS_TIMEZONE = /(?:Z|[+-]\d{2}:?\d{2})$/i;

export function parseApiTimestamp(iso: string): Date {
  return new Date(HAS_TIMEZONE.test(iso) ? iso : `${iso}Z`);
}

/** "2 hours ago", "yesterday", "just now" - for chat-history timestamps. */
export function relativeTime(iso: string): string {
  const then = parseApiTimestamp(iso).getTime();
  if (Number.isNaN(then)) return "";
  const elapsed = then - Date.now();
  const magnitude = Math.abs(elapsed);
  for (const [unit, ms] of UNITS) {
    if (magnitude >= ms) return formatter.format(Math.round(elapsed / ms), unit);
  }
  return "just now";
}
