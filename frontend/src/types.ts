// Mirrors backend/app/models/case_file.py - keep in sync by hand for now.
// A generated client (e.g. from FastAPI's OpenAPI schema) would remove this
// duplication risk; deferred as a later cleanup, not needed to ship Phase 1.

export interface ClassificationResult {
  applies: boolean | null;
  table_7_ref: string;
  applicable_clauses: string[];
  applicable_state_checklist_id: string | null;
  is_high_rise: boolean | null;
  require_human_review_flag: boolean;
  protection_level: string | null;
  notes: string[];
}

export interface FieldSource {
  value: unknown;
  source: "user" | "document" | "inferred" | "unknown";
  confidence: number;
}

export type ConversationStage = "intake" | "confirming" | "classified" | "report_ready";

export interface CaseFile {
  session_id: string;
  project_name: string;
  state: string;
  city: string;
  occupancy_type: string | null;
  occupancy_subdivision: string | null;
  industrial_hazard_band: string | null;
  height_m: number | null;
  is_high_rise: boolean | null;
  floors_above_ground: number | null;
  floors_below_ground: number | null;
  built_up_area_sqm: number | null;
  number_of_staircases: number | null;
  number_of_exits: number | null;
  existing_fire_systems: string[];
  field_sources: Record<string, FieldSource>;
  classification_result: ClassificationResult;
  conversation_stage: ConversationStage;
}

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
