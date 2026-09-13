import type { ChangeSource, FieldChange } from "../types";
import { formatLabel } from "./caseFileFields";

// Case File field names as a person would read them. formatLabel alone
// would render "height_m" as "Height M" and "built_up_area_sqm" as "Built
// Up Area Sqm"; anything not listed falls back to it, so a new Case File
// field shows up in the timeline with a serviceable label rather than not
// at all.
const FIELD_LABELS: Record<string, string> = {
  project_name: "Project name",
  state: "State",
  city: "City",
  occupancy_type: "Occupancy type",
  occupancy_subdivision: "Occupancy subdivision",
  industrial_hazard_band: "Industrial hazard band",
  mixed_occupancy: "Mixed occupancy",
  occupancy_breakdown: "Occupancy breakdown",
  height_m: "Height (m)",
  is_high_rise: "High rise",
  floors_above_ground: "Floors above ground",
  floors_below_ground: "Floors below ground",
  built_up_area_sqm: "Built-up area (sqm)",
  floor_wise_area: "Floor-wise area",
  number_of_staircases: "Staircases",
  number_of_exits: "Exits",
  existing_fire_systems: "Existing fire systems",
  kitchen_count: "Kitchens",
  door_count: "Doors",
  project_stage: "Project stage",
  goal: "Goal",
  code_edition: "Code edition",
  source_documents: "Source documents",
  conversation_stage: "Conversation stage",
};

export function changeFieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? formatLabel(field);
}

// Where a change came from, phrased as what actually happened rather than
// as the enum name. Mirrors backend/app/models/change_log.py's ChangeSource.
const SOURCE_LABELS: Record<ChangeSource, string> = {
  user: "Edited directly",
  dialogue: "From the conversation",
  document: "From a document",
  system: "System",
};

export function changeSourceLabel(source: ChangeSource): string {
  return SOURCE_LABELS[source] ?? formatLabel(source);
}

/** A change's old or new value, rendered for a one-line timeline entry. */
export function describeChangeValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not set";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) {
    if (value.length === 0) return "None";
    // A list of structured rows (occupancy_breakdown, floor_wise_area,
    // source_documents) has no useful one-line form - say how many there
    // are rather than dumping JSON into the timeline.
    if (value.some((item) => typeof item === "object" && item !== null)) {
      return `${value.length} ${value.length === 1 ? "entry" : "entries"}`;
    }
    return value.join(", ");
  }
  if (typeof value === "object") return "Updated";
  return String(value);
}

/** Groups changes made together (same source, same second) into one entry. */
export interface ChangeGroup {
  id: number;
  source: ChangeSource;
  actorUserId: string | null;
  createdAt: string;
  changes: FieldChange[];
}

// One edit, one document upload or one conversational turn can set several
// fields at once. Listing them as separate timeline entries repeats the
// same "when" and "from where" over and over, so consecutive changes that
// share both are shown as a single event.
export function groupChanges(changes: FieldChange[]): ChangeGroup[] {
  const groups: ChangeGroup[] = [];
  for (const change of changes) {
    const last = groups[groups.length - 1];
    if (last && last.source === change.source && last.createdAt === change.created_at) {
      last.changes.push(change);
      continue;
    }
    groups.push({
      id: change.id,
      source: change.source,
      actorUserId: change.actor_user_id,
      createdAt: change.created_at,
      changes: [change],
    });
  }
  return groups;
}
