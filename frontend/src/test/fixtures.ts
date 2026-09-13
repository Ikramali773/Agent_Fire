import type { CaseFile, ConversationMessage } from "../types";

// A minimal, valid CaseFile - the shape the backend actually sends, with
// every field present (Pydantic never omits one). Tests override only the
// handful of fields they care about, so adding a Case File field doesn't
// mean touching every test.
export function makeCaseFile(overrides: Partial<CaseFile> = {}): CaseFile {
  return {
    session_id: "session-1",
    owner_user_id: null,
    // project_name/state/city are plain strings with a "" default on the
    // backend, not nullable - the empty string IS the "not known yet" value.
    project_name: "",
    state: "",
    city: "",
    occupancy_type: null,
    occupancy_subdivision: null,
    industrial_hazard_band: null,
    mixed_occupancy: false,
    occupancy_breakdown: [],
    height_m: null,
    is_high_rise: null,
    floors_above_ground: null,
    floors_below_ground: null,
    built_up_area_sqm: null,
    floor_wise_area: [],
    number_of_staircases: null,
    number_of_exits: null,
    existing_fire_systems: [],
    kitchen_count: null,
    door_count: null,
    project_stage: null,
    goal: null,
    code_edition: "2026",
    source_documents: [],
    field_sources: {},
    classification_result: {
      applies: null,
      table_7_ref: "",
      applicable_clauses: [],
      applicable_state_checklist_id: null,
      is_high_rise: null,
      require_human_review_flag: false,
      review_reasons: [],
      protection_level: null,
      notes: [],
    },
    conversation_stage: "intake",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

export function makeMessage(overrides: Partial<ConversationMessage> = {}): ConversationMessage {
  return {
    id: 1,
    session_id: "session-1",
    role: "agent",
    kind: "text",
    text: "Hello",
    payload: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}
