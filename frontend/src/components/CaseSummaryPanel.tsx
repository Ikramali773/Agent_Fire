import type { CaseFile } from "../types";

interface Props {
  caseFile: CaseFile | null;
}

const FIELD_LABELS: Record<string, string> = {
  state: "State",
  city: "City",
  occupancy_type: "Occupancy",
  occupancy_subdivision: "Subdivision",
  industrial_hazard_band: "Hazard band",
  height_m: "Height (m)",
  floors_above_ground: "Floors above ground",
  floors_below_ground: "Floors below ground",
  built_up_area_sqm: "Built-up area (sqm)",
  number_of_staircases: "Staircases",
  number_of_exits: "Exits",
  existing_fire_systems: "Existing fire systems",
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
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
      {knownFields.length === 0 ? (
        <p className="summary-panel__empty">Nothing collected yet — answer the questions in chat.</p>
      ) : (
        <dl>
          {knownFields.map((name) => (
            <div className="summary-panel__row" key={name}>
              <dt>{FIELD_LABELS[name]}</dt>
              <dd>{formatValue((caseFile as unknown as Record<string, unknown>)[name])}</dd>
            </div>
          ))}
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
