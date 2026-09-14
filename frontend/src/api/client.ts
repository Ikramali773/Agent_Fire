import type {
  AuthResponse,
  CaseFile,
  CaseFileGrant,
  CaseFileInvite,
  CaseFilePage,
  ChatTitle,
  ChatTurnResponse,
  ConversationMessage,
  DocumentUploadResponse,
  FieldChange,
  InvitePreview,
  RequirementReport,
  ReviewQueueItem,
  ReviewState,
  ReviewStatus,
  User,
} from "../types";

// Vite exposes env vars prefixed VITE_ on import.meta.env. Default targets
// the backend's local dev port (see backend/README.md - uvicorn defaults to
// 8000). Override with VITE_API_BASE_URL for any other deployment.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// How many projects to fetch at a time. The chat rail shows 8 and Project
// History pages; nothing needs an account's whole history in one response.
export const PROJECT_PAGE_SIZE = 50;

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

// Phase 2 (accounts): set once after login/signup (see AuthContext), then
// automatically attached to every request below. An anonymous caller never
// sets this, so every existing Phase 1 flow (an anonymous case file, open
// to anyone with its session_id - see backend's _check_access) is
// completely unaffected.
let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

function authHeaders(): Record<string, string> {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {};
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders() },
    ...options,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(`${response.status} ${response.statusText}: ${body}`, response.status);
  }
  return response.json() as Promise<T>;
}

// For the endpoints that answer 204 with no body. Exists because every
// delete/logout call used to inline the same fetch-and-check block, and
// request<T> cannot be used: response.json() throws on an empty body.
async function requestNoContent(path: string, options?: RequestInit): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...authHeaders() },
    ...options,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(`${response.status} ${response.statusText}: ${body}`, response.status);
  }
}

// Shared by every binary download. Prefers the backend's own sanitized,
// project-name-derived filename (see exporters.py::safe_report_filename)
// and falls back to a generic one if the header is missing or malformed.
async function downloadFile(path: string, fallbackName: string): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`${API_BASE_URL}${path}`, { headers: authHeaders() });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(`${response.status} ${response.statusText}: ${body}`, response.status);
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]*)"/.exec(disposition)?.[1] ?? fallbackName;
  return { blob: await response.blob(), filename };
}

export const api = {
  signup: (email: string, password: string) =>
    request<AuthResponse>("/auth/signup", { method: "POST", body: JSON.stringify({ email, password }) }),

  login: (email: string, password: string) =>
    request<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  me: () => request<User>("/auth/me"),

  // Revokes the token server-side. Until this existed, signing out only
  // made this browser forget it while it stayed valid for the rest of its
  // seven-day life - anyone who had captured it still had the account.
  logout: () => requestNoContent("/auth/logout", { method: "POST" }),

  // Changing a password closes EVERY session on the account, this browser's
  // included (the backend stamps a cut-off - see user_store.set_password),
  // so callers must obtain a fresh token afterwards or the very next
  // request will 401. AuthContext.changePassword does that by re-logging
  // in; nothing else should call this directly.
  changePassword: (currentPassword: string, newPassword: string) =>
    requestNoContent("/auth/password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),

  // Always succeeds, whether or not the address has an account - the
  // backend deliberately answers the same either way so this cannot be
  // used to ask who uses the product. The UI must not claim a message was
  // sent to a real account, only that one was sent if the account exists.
  requestPasswordReset: (email: string) =>
    requestNoContent("/auth/password-reset/request", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  confirmPasswordReset: (token: string, newPassword: string) =>
    requestNoContent("/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    }),

  // Paged: the unbounded version grew linearly with an account's whole
  // history (0.81 MB of JSON at 500 projects) to render eight rail rows.
  myCaseFiles: (limit = PROJECT_PAGE_SIZE, offset = 0) =>
    request<CaseFilePage>(`/users/me/case-files?limit=${limit}&offset=${offset}`),

  // A title per chat, derived from its first user message - what lets the
  // sidebar tell projects apart before one has a name. A side-lookup, not
  // a Case File field: see the backend's ChatTitle.
  myChatTitles: (limit = PROJECT_PAGE_SIZE, offset = 0) =>
    request<ChatTitle[]>(`/users/me/chat-titles?limit=${limit}&offset=${offset}`),

  // Phase 3: every flagged case this account is responsible for - its own
  // projects plus ones shared with it for review. Oldest-first: a
  // compliance queue is FIFO, unlike the newest-first chat rail.
  myReviewQueue: (includeSettled = false) =>
    request<ReviewQueueItem[]>(`/users/me/review-queue${includeSettled ? "?include_settled=true" : ""}`),

  createCaseFile: () =>
    request<CaseFile>("/case-files", { method: "POST", body: "null" }),

  getCaseFile: (sessionId: string) => request<CaseFile>(`/case-files/${sessionId}`),

  // Deletes the project AND its whole chat transcript (the backend does
  // both in one step - see delete_case_file).
  deleteCaseFile: (sessionId: string) =>
    requestNoContent(`/case-files/${sessionId}`, { method: "DELETE" }),

  // The assistant's greeting for a case file that doesn't exist yet -
  // persists nothing, so simply opening the Overview page no longer
  // creates a project (see backend's get_opening_message).
  getOpeningMessage: () => request<{ agent_message: string }>("/case-files/opening-message"),

  getMessages: (sessionId: string) =>
    request<ConversationMessage[]>(`/case-files/${sessionId}/messages`),

  // The per-field change log, newest first. `beforeId` pages further back:
  // pass the id of the oldest change already held.
  getChanges: (sessionId: string, options: { limit?: number; beforeId?: number } = {}) => {
    const params = new URLSearchParams();
    if (options.limit !== undefined) params.set("limit", String(options.limit));
    if (options.beforeId !== undefined) params.set("before_id", String(options.beforeId));
    const query = params.toString();
    return request<FieldChange[]>(`/case-files/${sessionId}/changes${query ? `?${query}` : ""}`);
  },

  // Attaches a case file started while signed out to the account that is
  // now signed in. Only works on an unowned one (see claim_case_file).
  claimCaseFile: (sessionId: string) =>
    request<CaseFile>(`/case-files/${sessionId}/claim`, { method: "POST" }),

  startConversation: (sessionId: string) =>
    request<ChatTurnResponse>(`/case-files/${sessionId}/start`, { method: "POST" }),

  sendMessage: (sessionId: string, message: string) =>
    request<ChatTurnResponse>(`/case-files/${sessionId}/message`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  // Phase 4: per-requirement compliance findings. Derived on read from the
  // case file, so it never needs invalidating after an edit.
  getFindings: (sessionId: string) => request<RequirementReport>(`/case-files/${sessionId}/findings`),

  getReview: (sessionId: string) => request<ReviewState>(`/case-files/${sessionId}/review`),

  // Records a reviewer's verdict. Never rewrites the classification - see
  // the backend's record_review.
  recordReview: (sessionId: string, status: ReviewStatus, note: string) =>
    request<ReviewState>(`/case-files/${sessionId}/review`, {
      method: "POST",
      body: JSON.stringify({ status, note }),
    }),

  listShares: (sessionId: string) => request<CaseFileGrant[]>(`/case-files/${sessionId}/shares`),

  shareCaseFile: (sessionId: string, email: string) =>
    request<CaseFileGrant>(`/case-files/${sessionId}/shares`, {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  revokeShare: (sessionId: string, grantedToUserId: string) =>
    requestNoContent(`/case-files/${sessionId}/shares/${grantedToUserId}`, { method: "DELETE" }),

  // Phase 4 invites. Sharing by email only reaches someone who already has
  // an account; an invite link reaches the consultant who does not.
  listInvites: (sessionId: string) => request<CaseFileInvite[]>(`/case-files/${sessionId}/invites`),

  // The response carries `invite_url` exactly once - the token is stored
  // hashed, so a link that isn't copied here cannot be recovered, only
  // revoked and reissued.
  createInvite: (sessionId: string, email: string) =>
    request<CaseFileInvite>(`/case-files/${sessionId}/invites`, {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  revokeInvite: (sessionId: string, invitedEmail: string) =>
    requestNoContent(`/case-files/${sessionId}/invites/${encodeURIComponent(invitedEmail)}`, {
      method: "DELETE",
    }),

  // Unauthenticated on purpose: the recipient has no account yet, and
  // being asked to create one without being told what for is how an
  // invitation gets ignored.
  previewInvite: (token: string) => request<InvitePreview>(`/invites/${encodeURIComponent(token)}`),

  acceptInvite: (token: string) =>
    request<CaseFileInvite>(`/invites/${encodeURIComponent(token)}/accept`, { method: "POST" }),

  getHandoff: (sessionId: string) => request<{ markdown: string }>(`/case-files/${sessionId}/handoff`),

  getReport: (sessionId: string) =>
    request<{ markdown: string }>(`/case-files/${sessionId}/report`),

  // Pass the `version` from the case file you are editing and the server
  // refuses the write with a 409 if someone else changed it in between,
  // instead of silently overwriting them. Callers surface that as "reload
  // and try again" - never as an automatic retry, which would reintroduce
  // exactly the overwrite this prevents.
  updateCaseFile: (sessionId: string, updates: Record<string, unknown>, version?: number) =>
    request<CaseFile>(`/case-files/${sessionId}`, {
      method: "PUT",
      body: JSON.stringify(version === undefined ? updates : { ...updates, version }),
    }),

  whatIf: (sessionId: string, updates: Record<string, unknown>) =>
    // Phase 2: reclassifies a hypothetical copy of the case file - never
    // persisted server-side (see backend/app/api/case_files.py's
    // what_if_case_file, which deliberately never calls store_save()).
    request<CaseFile>(`/case-files/${sessionId}/what-if`, {
      method: "POST",
      body: JSON.stringify(updates),
    }),

  downloadReport: async (sessionId: string, format: "pdf" | "docx"): Promise<{ blob: Blob; filename: string }> =>
    downloadFile(`/case-files/${sessionId}/report.${format}`, `report.${format}`),

  downloadHandoff: async (sessionId: string, format: "pdf" | "docx"): Promise<{ blob: Blob; filename: string }> =>
    downloadFile(`/case-files/${sessionId}/handoff.${format}`, `reviewer-handoff.${format}`),

  uploadDocument: async (sessionId: string, file: File): Promise<DocumentUploadResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    // No Content-Type header here on purpose - the browser sets
    // multipart/form-data with the correct boundary itself; setting it
    // manually (as the JSON request() helper above does) breaks the upload.
    const response = await fetch(`${API_BASE_URL}/case-files/${sessionId}/documents`, {
      method: "POST",
      body: formData,
      headers: authHeaders(),
    });
    if (!response.ok) {
      const body = await response.text();
      throw new ApiError(`${response.status} ${response.statusText}: ${body}`, response.status);
    }
    return response.json() as Promise<DocumentUploadResponse>;
  },
};

export { ApiError };
