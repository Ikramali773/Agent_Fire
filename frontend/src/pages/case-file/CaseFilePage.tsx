import { useState } from "react";
import { api, ApiError } from "../../api/client";
import { Card } from "../../design-system/components/Card";
import { DataRow } from "../../design-system/components/DataRow";
import { EmptyState } from "../../design-system/components/EmptyState";
import { StatusPill } from "../../design-system/components/StatusPill";
import { fieldMeta, formatLabel, formatValue, normalizeClassification } from "../../lib/caseFileFields";
import { ReviewBanner } from "../review/ReviewBanner";
import { useAuth } from "../../auth/AuthContext";
import { isReadOnlyCaseFile } from "../../lib/access";
import type { CaseFile } from "../../types";
import { ActivityTimeline } from "./ActivityTimeline";
import { parseBoolean, parseNumberOrNull, parseStringList } from "./editableFields";
import "./CaseFilePage.css";

interface Props {
  caseFile: CaseFile | null;
  onCaseFileChange: (caseFile: CaseFile) => void;
  onGoToReview: () => void;
}

export function CaseFilePage({ caseFile, onCaseFileChange, onGoToReview }: Props) {
  const { user } = useAuth();
  const [error, setError] = useState<string | null>(null);
  // Bumped after every successful save so the history below picks up the
  // change that was just made, without refetching it on every render.
  const [historyKey, setHistoryKey] = useState(0);

  if (!caseFile) {
    return (
      <div className="ds-case-file-page">
        <EmptyState title="No active case yet" description="Start a conversation on the Overview page to begin building the case file." />
      </div>
    );
  }

  // DataRow shows its edit affordance only when given an onSave, so
  // withholding it on a project this user cannot write to removes the
  // pencil entirely rather than offering an edit the server will refuse.
  const readOnly = isReadOnlyCaseFile(caseFile, user);
  const editable = <T,>(handler: T): T | undefined => (readOnly ? undefined : handler);

  const save = async (key: string, value: unknown) => {
    setError(null);
    try {
      // The version turns this into a compare-and-set: if someone else
      // changed the project since this page loaded, the server refuses
      // rather than quietly overwriting them.
      const updated = await api.updateCaseFile(caseFile.session_id, { [key]: value }, caseFile.version);
      onCaseFileChange(updated);
      setHistoryKey((key) => key + 1);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Never retried automatically - that would reintroduce exactly the
        // overwrite the version check exists to prevent.
        setError(
          "Someone else changed this project while you had it open. Reload the page to see their changes, then make yours again.",
        );
        return;
      }
      setError(err instanceof ApiError ? `Could not save that change (${err.status}). ${err.message}` : "Could not save that change.");
    }
  };

  const classification = normalizeClassification(caseFile.classification_result);

  return (
    <div className="ds-case-file-page">
      <header className="ds-case-file-page__header">
        <h1>{caseFile.project_name || "Untitled project"}</h1>
        <p className="ds-case-file-page__subhead">
          Every field below shows where it came from and how confident the system is. An edit here saves immediately and is
          recorded as user-confirmed, replacing whatever the value's earlier source was.
        </p>
      </header>

      <ReviewBanner result={classification} onGoToReview={onGoToReview} />

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
            onSave={editable((v) => save("project_name", v))}
            {...fieldMeta(caseFile, "project_name")}
          />
          <DataRow
            label="State"
            value={formatValue(caseFile.state)}
            editValue={caseFile.state}
            onSave={editable((v) => save("state", v))}
            {...fieldMeta(caseFile, "state")}
          />
          <DataRow
            label="City"
            value={formatValue(caseFile.city)}
            editValue={caseFile.city}
            onSave={editable((v) => save("city", v))}
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
            onSave={editable((v) => save("height_m", parseNumberOrNull(v)))}
            {...fieldMeta(caseFile, "height_m")}
          />
          <DataRow
            label="High rise"
            value={formatValue(caseFile.is_high_rise)}
            editValue={caseFile.is_high_rise ? "yes" : "no"}
            onSave={editable((v) => save("is_high_rise", parseBoolean(v)))}
            {...fieldMeta(caseFile, "is_high_rise")}
          />
          <DataRow
            label="Floors above ground"
            value={formatValue(caseFile.floors_above_ground)}
            editValue={caseFile.floors_above_ground?.toString() ?? ""}
            onSave={editable((v) => save("floors_above_ground", parseNumberOrNull(v)))}
            {...fieldMeta(caseFile, "floors_above_ground")}
          />
          <DataRow
            label="Floors below ground"
            value={formatValue(caseFile.floors_below_ground)}
            editValue={caseFile.floors_below_ground?.toString() ?? ""}
            onSave={editable((v) => save("floors_below_ground", parseNumberOrNull(v)))}
            {...fieldMeta(caseFile, "floors_below_ground")}
          />
          <DataRow
            label="Built-up area (sqm)"
            value={formatValue(caseFile.built_up_area_sqm)}
            editValue={caseFile.built_up_area_sqm?.toString() ?? ""}
            onSave={editable((v) => save("built_up_area_sqm", parseNumberOrNull(v)))}
            {...fieldMeta(caseFile, "built_up_area_sqm")}
          />
          <DataRow
            label="Kitchens"
            value={formatValue(caseFile.kitchen_count)}
            editValue={caseFile.kitchen_count?.toString() ?? ""}
            onSave={editable((v) => save("kitchen_count", parseNumberOrNull(v)))}
            {...fieldMeta(caseFile, "kitchen_count")}
          />
          <DataRow
            label="Doors"
            value={formatValue(caseFile.door_count)}
            editValue={caseFile.door_count?.toString() ?? ""}
            onSave={editable((v) => save("door_count", parseNumberOrNull(v)))}
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
            onSave={editable((v) => save("number_of_staircases", parseNumberOrNull(v)))}
            {...fieldMeta(caseFile, "number_of_staircases")}
          />
          <DataRow
            label="Exits"
            value={formatValue(caseFile.number_of_exits)}
            editValue={caseFile.number_of_exits?.toString() ?? ""}
            onSave={editable((v) => save("number_of_exits", parseNumberOrNull(v)))}
            {...fieldMeta(caseFile, "number_of_exits")}
          />
        </Card>

        <Card title="Fire systems" padded={false}>
          <DataRow
            label="Existing systems"
            value={formatValue(caseFile.existing_fire_systems)}
            editValue={caseFile.existing_fire_systems.join(", ")}
            onSave={editable((v) => save("existing_fire_systems", parseStringList(v)))}
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
        <Card title="History">
          {/* The per-field audit trail. Project History is a project LIST
              showing each case file's current state; this is the "what
              changed, when, and off the back of what" for this one. */}
          <ActivityTimeline sessionId={caseFile.session_id} refreshKey={historyKey} />
        </Card>
      </div>
    </div>
  );
}
