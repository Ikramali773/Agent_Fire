import type {
  AuthResponse,
  CaseFile,
  ChatTurnResponse,
  ConversationMessage,
  DocumentUploadResponse,
  User,
} from "../types";

// Vite exposes env vars prefixed VITE_ on import.meta.env. Default targets
// the backend's local dev port (see backend/README.md - uvicorn defaults to
// 8000). Override with VITE_API_BASE_URL for any other deployment.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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

export const api = {
  signup: (email: string, password: string) =>
    request<AuthResponse>("/auth/signup", { method: "POST", body: JSON.stringify({ email, password }) }),

  login: (email: string, password: string) =>
    request<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  me: () => request<User>("/auth/me"),

  myCaseFiles: () => request<CaseFile[]>("/users/me/case-files"),

  createCaseFile: () =>
    request<CaseFile>("/case-files", { method: "POST", body: "null" }),

  getCaseFile: (sessionId: string) => request<CaseFile>(`/case-files/${sessionId}`),

  // Deletes the project AND its whole chat transcript (the backend does
  // both in one step - see delete_case_file). Not routed through request()
  // because a 204 has no body to parse.
  deleteCaseFile: async (sessionId: string): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/case-files/${sessionId}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    if (!response.ok) {
      const body = await response.text();
      throw new ApiError(`${response.status} ${response.statusText}: ${body}`, response.status);
    }
  },

  // The assistant's greeting for a case file that doesn't exist yet -
  // persists nothing, so simply opening the Overview page no longer
  // creates a project (see backend's get_opening_message).
  getOpeningMessage: () => request<{ agent_message: string }>("/case-files/opening-message"),

  getMessages: (sessionId: string) =>
    request<ConversationMessage[]>(`/case-files/${sessionId}/messages`),

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

  getReport: (sessionId: string) =>
    request<{ markdown: string }>(`/case-files/${sessionId}/report`),

  updateCaseFile: (sessionId: string, updates: Record<string, unknown>) =>
    request<CaseFile>(`/case-files/${sessionId}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    }),

  whatIf: (sessionId: string, updates: Record<string, unknown>) =>
    // Phase 2: reclassifies a hypothetical copy of the case file - never
    // persisted server-side (see backend/app/api/case_files.py's
    // what_if_case_file, which deliberately never calls store_save()).
    request<CaseFile>(`/case-files/${sessionId}/what-if`, {
      method: "POST",
      body: JSON.stringify(updates),
    }),

  downloadReport: async (sessionId: string, format: "pdf" | "docx"): Promise<{ blob: Blob; filename: string }> => {
    const response = await fetch(`${API_BASE_URL}/case-files/${sessionId}/report.${format}`, {
      headers: authHeaders(),
    });
    if (!response.ok) {
      const body = await response.text();
      throw new ApiError(`${response.status} ${response.statusText}: ${body}`, response.status);
    }
    // Prefer the backend's own sanitized, project-name-derived filename
    // (see backend/app/reports/exporters.py::safe_report_filename); fall
    // back to a generic one if the header is ever missing/malformed.
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const filename = /filename="([^"]*)"/.exec(disposition)?.[1] ?? `report.${format}`;
    const blob = await response.blob();
    return { blob, filename };
  },

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
