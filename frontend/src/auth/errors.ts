import { ApiError } from "../api/client";

// Every auth surface has to turn an ApiError into something a person can
// act on, and they were all doing it slightly differently. The raw message
// is "422 Unprocessable Entity: {"detail":"..."}" - useful in a log, not on
// screen - so unwrap the backend's own detail where there is one, and give
// the two statuses that carry no useful body a sentence of their own.
export function authErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  if (error.status === 429) return "Too many attempts. Wait a moment and try again.";
  const detail = extractDetail(error.message);
  return detail ?? fallback;
}

function extractDetail(message: string): string | null {
  const body = message.replace(/^\d+ [^:]*:\s*/, "");
  try {
    const parsed: unknown = JSON.parse(body);
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      const detail = (parsed as { detail: unknown }).detail;
      // FastAPI's validation errors put a list here, not a sentence. Those
      // are developer-facing; a caller's own fallback reads better.
      if (typeof detail === "string" && detail.trim()) return detail;
    }
    return null;
  } catch {
    return body.trim() ? body : null;
  }
}
