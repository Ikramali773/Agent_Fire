import { FlaskConical, X } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "../../api/client";
import { Badge } from "../../design-system/components/Badge";
import { Button } from "../../design-system/components/Button";
import { Card } from "../../design-system/components/Card";
import { StatusPill } from "../../design-system/components/StatusPill";
import { normalizeClassification } from "../../lib/caseFileFields";
import type { CaseFile } from "../../types";
import { clauseStatus, overallStatus } from "./complianceStatus";
import "./WhatIfPanel.css";

const OCCUPANCY_OPTIONS = [
  "Residential",
  "Educational",
  "Institutional",
  "Assembly",
  "Business",
  "Mercantile",
  "Industrial",
  "Storage",
  "Hazardous",
  "Mixed Use",
] as const;

interface Props {
  caseFile: CaseFile;
}

// Phase 2: "what if this field were X" - lets a user explore a scenario
// against the real classifier without ever touching the saved case file.
// The backend's /what-if endpoint reclassifies a hypothetical copy and
// never persists it (see backend/app/api/case_files.py), so this panel's
// only job is to make it unmistakably clear the result on screen is a
// scenario, never the building's real, saved classification.
export function WhatIfPanel({ caseFile }: Props) {
  const [open, setOpen] = useState(false);
  const [heightM, setHeightM] = useState(caseFile.height_m?.toString() ?? "");
  const [builtUpAreaSqm, setBuiltUpAreaSqm] = useState(caseFile.built_up_area_sqm?.toString() ?? "");
  const [floorsAboveGround, setFloorsAboveGround] = useState(caseFile.floors_above_ground?.toString() ?? "");
  const [occupancyType, setOccupancyType] = useState(caseFile.occupancy_type ?? "");
  const [result, setResult] = useState<CaseFile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRecompute = async () => {
    setLoading(true);
    setError(null);
    try {
      const hypothetical = await api.whatIf(caseFile.session_id, {
        height_m: heightM.trim() ? Number(heightM) : null,
        built_up_area_sqm: builtUpAreaSqm.trim() ? Number(builtUpAreaSqm) : null,
        floors_above_ground: floorsAboveGround.trim() ? Number(floorsAboveGround) : null,
        occupancy_type: occupancyType || null,
      });
      setResult(hypothetical);
    } catch (err) {
      setError(err instanceof ApiError ? `Could not recompute the scenario (${err.status}).` : "Could not recompute the scenario.");
    } finally {
      setLoading(false);
    }
  };

  const handleDiscard = () => {
    setResult(null);
    setError(null);
    setOpen(false);
  };

  if (!open) {
    return (
      <Button variant="secondary" size="sm" icon={<FlaskConical />} onClick={() => setOpen(true)}>
        Try a what-if scenario
      </Button>
    );
  }

  const hypotheticalResult = result ? normalizeClassification(result.classification_result) : null;

  return (
    <Card
      title={
        <span className="ds-what-if__title">
          What-if scenario
          <Badge tone="phase">Hypothetical — not saved</Badge>
        </span>
      }
      actions={
        <button type="button" className="ds-what-if__close" onClick={handleDiscard} aria-label="Discard scenario">
          <X aria-hidden="true" />
        </button>
      }
    >
      <p className="ds-what-if__note">
        Try a different value for one or more fields and recompute - this never changes the real case file.
      </p>

      <div className="ds-what-if__fields">
        <label className="ds-what-if__field">
          <span>Height (m)</span>
          <input type="number" value={heightM} onChange={(e) => setHeightM(e.target.value)} />
        </label>
        <label className="ds-what-if__field">
          <span>Built-up area (sqm)</span>
          <input type="number" value={builtUpAreaSqm} onChange={(e) => setBuiltUpAreaSqm(e.target.value)} />
        </label>
        <label className="ds-what-if__field">
          <span>Floors above ground</span>
          <input type="number" value={floorsAboveGround} onChange={(e) => setFloorsAboveGround(e.target.value)} />
        </label>
        <label className="ds-what-if__field">
          <span>Occupancy type</span>
          <select value={occupancyType} onChange={(e) => setOccupancyType(e.target.value)}>
            <option value="">Not set</option>
            {OCCUPANCY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="ds-what-if__actions">
        <Button variant="primary" size="sm" onClick={handleRecompute} disabled={loading}>
          {loading ? "Recomputing…" : "Recompute"}
        </Button>
        <Button variant="ghost" size="sm" onClick={handleDiscard}>
          Discard scenario
        </Button>
      </div>

      {error && (
        <div className="ds-what-if__error" role="alert">
          {error}
        </div>
      )}

      {hypotheticalResult && (
        <div className="ds-what-if__result">
          <div className="ds-what-if__result-header">
            <StatusPill status={overallStatus(hypotheticalResult)} />
            <span>
              Table 7 reference: <strong>{hypotheticalResult.table_7_ref || "Not yet known"}</strong>
              {hypotheticalResult.protection_level && (
                <>
                  {" "}
                  | Protection level: <strong>{hypotheticalResult.protection_level}</strong>
                </>
              )}
            </span>
          </div>
          {hypotheticalResult.applicable_clauses.length > 0 && (
            <ul className="ds-what-if__clauses">
              {hypotheticalResult.applicable_clauses.map((clause) => (
                <li key={clause}>
                  <StatusPill status={clauseStatus(hypotheticalResult)} size="sm" />
                  <span>{clause}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
