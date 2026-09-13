// Generated from the backend's OpenAPI schema - see api/schema.ts and this
// repo's frontend/README.md "Generated API types" section for the
// regeneration workflow (backend/scripts/export_openapi.py +
// `npm run generate:types`). This file only re-derives the specific named
// types the app uses, with Required<> applied: FastAPI/Pydantic marks any
// field with a default as "not required" in the OpenAPI spec (a request
// could omit it), but a *response* the backend actually sends always
// includes every field with its current value (Pydantic serialization
// never omits a field) - so consuming code can safely treat these as
// always-present, same guarantee the old hand-written interfaces gave.
import type { components } from "./api/schema";

export type ClassificationResult = Required<components["schemas"]["ClassificationResult"]>;
export type FieldSource = Required<components["schemas"]["FieldSource"]>;
export type ConversationStage = components["schemas"]["ConversationStage"];
export type OccupancyBreakdownItem = Required<components["schemas"]["OccupancyBreakdownItem"]>;
export type FloorAreaItem = components["schemas"]["FloorAreaItem"];
export type CaseFile = Required<components["schemas"]["CaseFile"]>;
export type User = Required<components["schemas"]["User"]>;
export type AuthResponse = Required<components["schemas"]["AuthResponse"]>;
export type ConversationMessage = Required<components["schemas"]["ConversationMessage"]>;
export type FieldChange = Required<components["schemas"]["FieldChange"]>;
export type ChatTitle = Required<components["schemas"]["ChatTitle"]>;
export type ReviewReason = Required<components["schemas"]["ReviewReason"]>;
export type ReviewReasonCode = components["schemas"]["ReviewReasonCode"];
export type ReviewStatus = components["schemas"]["ReviewStatus"];
export type ReviewEvent = Required<components["schemas"]["ReviewEvent"]>;
export type ReviewState = Required<components["schemas"]["ReviewState"]>;
export type ReviewQueueItem = Required<components["schemas"]["ReviewQueueItem"]>;
export type CaseFileGrant = Required<components["schemas"]["CaseFileGrant"]>;
// Required<> is SHALLOW, so it would leave `items` as the raw, partly
// optional CaseFile rather than the Required one exported above - the same
// trap normalizeClassification exists for. Re-point `items` explicitly.
export type CaseFilePage = Omit<Required<components["schemas"]["CaseFilePage"]>, "items"> & {
  items: CaseFile[];
};
export type ChangeSource = components["schemas"]["ChangeSource"];

export interface ChatTurnResponse {
  agent_message: string;
  case_file: CaseFile;
}

export interface IngestSummary {
  tier_used: number;
  confidence: number;
  needs_human_review: boolean;
  fields_extracted: string[];
  failure_reason: string | null;
  fact_extraction_skipped_reason: string | null;
}

export interface DocumentUploadResponse {
  summary: IngestSummary;
  case_file: CaseFile;
}

export interface ChatMessage {
  role: "agent" | "user";
  text: string;
}
