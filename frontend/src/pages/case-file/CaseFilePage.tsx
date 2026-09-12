import { useState } from "react";
import { api, ApiError } from "../../api/client";
import { Card } from "../../design-system/components/Card";
import { DataRow } from "../../design-system/components/DataRow";
import { EmptyState } from "../../design-system/components/EmptyState";
import { StatusPill } from "../../design-system/components/StatusPill";
import { fieldMeta, formatLabel, formatValue } from "../../lib/caseFileFields";
import type { CaseFile } from "../../types";
import { parseBoolean, parseNumberOrNull, parseStringList } from "./editableFields";
import "./CaseFilePage.css";

interface Props {
  caseFile: CaseFile | null;
  onCaseFileChange: (caseFile: CaseFile) => void;
}

export function CaseFilePage({ caseFile, onCaseFileChange }: Props) {
  const [error, setError] = useState<string | null>(null);

  if (!caseFile) {
    return (
      <div className="ds-case-file-page">
        <EmptyState title="No active case yet" description="Start a conversation on the Overview page to begin building the case file." />
      </div>
    );
  }

  const save = async (key: string, value: unknown) => {
    setError(null);
    try {
      const updated = await api.updateCaseFile(caseFile.session_id, { [key]: value });
      onCaseFileChange(updated);
    } catch (err) {
      setError(err instanceof ApiError ? `Could not save that change (${err.status}). ${err.message}` : "Could not save that change.");
    }
  };

  const classification = caseFile.classification_result;

  return (
    <div className="ds-case-file-page">
      <header className="ds-case-file-page__header">
        <h1>{caseFile.project_name || "Untitled project"}</h1>
        <p className="ds-case-file-page__subhead">
          Every field below shows where it came from and how confident the system is. Edits save immediately, but the source label
          won't switch to "User" until a future update — treat it as informational until then.
        </p>
      </header>

      {error && (
        <div className="ds-case-file-page__error" role="alert">
          {error}
        </div>
      )}

      <div className="ds-case-file-page__sections">
        <Card title="Project" padded={false}>
          <DataRow
            label="Project name"
            value={formatValue(caseFile.project_name)}
            editValue={caseFile.project_name}
            onSave={(v) => save("project_name", v)}
            {...fieldMeta(caseFile, "project_name")}
          />
          <DataRow
            label="State"
            value={formatValue(caseFile.state)}
            editValue={caseFile.state}
            onSave={(v) => save("state", v)}
            {...fieldMeta(caseFile, "state")}
          />
          <DataRow
            label="City"
            value={formatValue(caseFile.city)}
            editValue={caseFile.city}
            onSave={(v) => save("city", v)}
            {...fieldMeta(caseFile, "city")}
          />
          <DataRow label="Project stage" value={formatLabel(caseFile.project_stage)} {...fieldMeta(caseFile, "project_stage")} />
          <DataRow label="Goal" value={formatLabel(caseFile.goal)} {...fieldMeta(caseFile, "goal")} />
          <DataRow label="Code edition" value={caseFile.code_edition === "2026" ? "NBCS 2026 (primary)" : "NBC 2016 (legacy)"} />
        </Card>

        <Card title="Classification" padded={false}>
          <DataRow label="Occupancy type" value={formatValue(caseFile.occupancy_type)} {...fieldMeta(caseFile, "occupancy_type")} />
          <DataRow
            label="Occupancy subdivision"
            value={formatValue(caseFile.occupancy_subdivision)}
            {...fieldMeta(caseFile, "occupancy_subdivision")}
          />
          <DataRow label="Mixed occupancy" value={caseFile.mixed_occupancy ? "Yes" : "No"} {...fieldMeta(caseFile, "mixed_occupancy")} />
          <DataRow
            label="Industrial hazard band"
            value={formatValue(caseFile.industrial_hazard_band)}
            {...fieldMeta(caseFile, "industrial_hazard_band")}
          />
        </Card>

        {caseFile.occupancy_breakdown.length > 0 && (
          <Card title="Occupancy breakdown">
            <table className="ds-case-file-page__table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Floor range</th>
                  <th>Area (sqm)</th>
                  <th>Subdivision</th>
                </tr>
              </thead>
              <tbody>
                {caseFile.occupancy_breakdown.map((item, index) => (
                  <tr key={index}>
                    <td>{item.type}</td>
                    <td>{item.floor_range}</td>
                    <td className="tabular-nums">{item.floor_area_sqm ?? "—"}</td>
                    <td>{item.subdivision ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}

        <Card title="Building" padded={false}>
          <DataRow
            label="Height (m)"
            value={formatValue(caseFile.height_m)}
            editValue={caseFile.height_m?.toString() ?? ""}
            onSave={(v) => save("height_m", parseNumberOrNull(v))}
            {...fieldMeta(caseFile, "height_m")}
          />
          <DataRow
            label="High rise"
            value={formatValue(caseFile.is_high_rise)}
            editValue={caseFile.is_high_rise ? "yes" : "no"}
            onSave={(v) => save("is_high_rise", parseBoolean(v))}
            {...fieldMeta(caseFile, "is_high_rise")}
          />
          <DataRow
            label="Floors above ground"
            value={formatValue(caseFile.floors_above_ground)}
            editValue={caseFile.floors_above_ground?.toString() ?? ""}
            onSave={(v) => save("floors_above_ground", parseNumberOrNull(v))}
            {...fieldMeta(caseFile, "floors_above_ground")}
          />
          <DataRow
            label="Floors below ground"
            value={formatValue(caseFile.floors_below_ground)}
            editValue={caseFile.floors_below_ground?.toString() ?? ""}
            onSave={(v) => save("floors_below_ground", parseNumberOrNull(v))}
            {...fieldMeta(caseFile, "floors_below_ground")}
          />
          <DataRow
            label="Built-up area (sqm)"
            value={formatValue(caseFile.built_up_area_sqm)}
            editValue={caseFile.built_up_area_sqm?.toString() ?? ""}
            onSave={(v) => save("built_up_area_sqm", parseNumberOrNull(v))}
            {...fieldMeta(caseFile, "built_up_area_sqm")}
          />
          <DataRow
            label="Kitchens"
            value={formatValue(caseFile.kitchen_count)}
            editValue={caseFile.kitchen_count?.toString() ?? ""}
            onSave={(v) => save("kitchen_count", parseNumberOrNull(v))}
            {...fieldMeta(caseFile, "kitchen_count")}
          />
          <DataRow
            label="Doors"
            value={formatValue(caseFile.door_count)}
            editValue={caseFile.door_count?.toString() ?? ""}
            onSave={(v) => save("door_count", parseNumberOrNull(v))}
            {...fieldMeta(caseFile, "door_count")}
          />
        </Card>

        {caseFile.floor_wise_area.length > 0 && (
          <Card title="Floor-wise area">
            <table className="ds-case-file-page__table">
              <thead>
                <tr>
                  <th>Floor</th>
                  <th>Area (sqm)</th>
                </tr>
              </thead>
              <tbody>
                {caseFile.floor_wise_area.map((item, index) => (
                  <tr key={index}>
                    <td>{item.floor}</td>
                    <td className="tabular-nums">{item.area_sqm}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}

        <Card title="Egress" padded={false}>
          <DataRow
            label="Staircases"
            value={formatValue(caseFile.number_of_staircases)}
            editValue={caseFile.number_of_staircases?.toString() ?? ""}
            onSave={(v) => save("number_of_staircases", parseNumberOrNull(v))}
            {...fieldMeta(caseFile, "number_of_staircases")}
          />
          <DataRow
            label="Exits"
            value={formatValue(caseFile.number_of_exits)}
            editValue={caseFile.number_of_exits?.toString() ?? ""}
            onSave={(v) => save("number_of_exits", parseNumberOrNull(v))}
            {...fieldMeta(caseFile, "number_of_exits")}
          />
        </Card>

        <Card title="Fire systems" padded={false}>
          <DataRow
            label="Existing systems"
            value={formatValue(caseFile.existing_fire_systems)}
            editValue={caseFile.existing_fire_systems.join(", ")}
            onSave={(v) => save("existing_fire_systems", parseStringList(v))}
            {...fieldMeta(caseFile, "existing_fire_systems")}
          />
        </Card>

        <Card title="Classification result">
          {classification.table_7_ref ? (
            <>
              <div className="ds-case-file-page__classification-status">
                {classification.require_human_review_flag ? <StatusPill status="human_review" /> : <StatusPill status="info" label="Complete" />}
              </div>
              <DataRow label="Table 7 reference" value={formatValue(classification.table_7_ref)} />
              <DataRow label="Protection level" value={formatValue(classification.protection_level)} />
              <DataRow label="High rise" value={formatValue(classification.is_high_rise)} />
              <DataRow label="Applicable clauses" value={formatValue(classification.applicable_clauses)} />
            </>
          ) : (
            <p className="ds-case-file-page__note">Not classified yet — continue the conversation on the Overview page.</p>
          )}
        </Card>

        {caseFile.source_documents.length > 0 && (
          <Card title="Source documents">
            <table className="ds-case-file-page__table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Pages</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {caseFile.source_documents.map((doc, index) => (
                  <tr key={index}>
                    <td>{doc.filename}</td>
                    <td className="tabular-nums">{doc.pages}</td>
                    <td className="tabular-nums">{Math.round(doc.overall_confidence * 100)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  );
}
