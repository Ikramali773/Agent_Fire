import type { CaseFile, FloorAreaItem, OccupancyBreakdownItem } from "../types";

interface Props {
  caseFile: CaseFile | null;
}

const FIELD_LABELS: Record<string, string> = {
  state: "State",
  city: "City",
  occupancy_type: "Occupancy",
  occupancy_subdivision: "Subdivision",
  industrial_hazard_band: "Hazard band",
  occupancy_breakdown: "Occupancy breakdown",
  height_m: "Height (m)",
  floors_above_ground: "Floors above ground",
  floors_below_ground: "Floors below ground",
  built_up_area_sqm: "Built-up area (sqm)",
  number_of_staircases: "Staircases",
  number_of_exits: "Exits",
  existing_fire_systems: "Existing fire systems",
};

// floor_wise_area has no intake node (document-upload-only, see backend
// dialogue/nodes.py) so it isn't gated by field_sources the way the fields
// above are - it's shown separately, below, whenever the list is non-empty.

function formatOccupancyBreakdown(items: OccupancyBreakdownItem[]): string {
  return items
    .map((item) => {
      let bit = `${item.type} (${item.floor_range}`;
      if (item.floor_area_sqm !== null) bit += `, ${item.floor_area_sqm} sqm`;
      if (item.subdivision) bit += `, ${item.subdivision}`;
      return bit + ")";
    })
    .join("; ");
}

function formatFloorWiseArea(items: FloorAreaItem[]): string {
  return items.map((item) => `${item.floor}: ${item.area_sqm} sqm`).join("; ");
}

function formatValue(name: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (name === "occupancy_breakdown") return formatOccupancyBreakdown(value as OccupancyBreakdownItem[]);
  if (Array.isArray(value)) return value.length ? value.join(", ") : "None";
  return String(value);
}

export function CaseSummaryPanel({ caseFile }: Props) {
  if (!caseFile) return null;

  const knownFields = Object.keys(FIELD_LABELS).filter(
    (name) => name in caseFile.field_sources,
  );

  const result = caseFile.classification_result;

  return (
    <aside className="summary-panel">
      <h2>Case summary</h2>
      {knownFields.length === 0 && caseFile.floor_wise_area.length === 0 ? (
        <p className="summary-panel__empty">Nothing collected yet — answer the questions in chat.</p>
      ) : (
        <dl>
          {knownFields.map((name) => (
            <div className="summary-panel__row" key={name}>
              <dt>{FIELD_LABELS[name]}</dt>
              <dd>{formatValue(name, (caseFile as unknown as Record<string, unknown>)[name])}</dd>
            </div>
          ))}
          {caseFile.floor_wise_area.length > 0 && (
            <div className="summary-panel__row">
              <dt>Floor-wise area</dt>
              <dd>{formatFloorWiseArea(caseFile.floor_wise_area)}</dd>
            </div>
          )}
        </dl>
      )}

      {caseFile.conversation_stage === "classified" && (
        <div className="summary-panel__result">
          <h3>Classification</h3>
          <p>
            Applies to Part F: <strong>{String(result.applies)}</strong>
          </p>
          {result.table_7_ref && (
            <p>
              Table 7 reference: <strong>{result.table_7_ref}</strong>
              {result.protection_level && ` (${result.protection_level})`}
            </p>
          )}
          {result.is_high_rise !== null && (
            <p>
              High rise: <strong>{result.is_high_rise ? "Yes" : "No"}</strong>
            </p>
          )}
          {result.require_human_review_flag && (
            <p className="summary-panel__warning">⚠ Requires human/expert review</p>
          )}
        </div>
      )}
    </aside>
  );
}
