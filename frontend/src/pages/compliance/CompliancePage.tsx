import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Button } from "../../design-system/components/Button";
import { Card } from "../../design-system/components/Card";
import { EmptyState } from "../../design-system/components/EmptyState";
import { StatusPill } from "../../design-system/components/StatusPill";
import { normalizeClassification } from "../../lib/caseFileFields";
import { ReviewBanner } from "../review/ReviewBanner";
import { findingLabel, findingsSummaryTone, findingTone } from "../../lib/findings";
import type { CaseFile, RequirementReport } from "../../types";
import { clauseStatus, overallStatus } from "./complianceStatus";
import { WhatIfPanel } from "./WhatIfPanel";
import "./CompliancePage.css";

interface Props {
  caseFile: CaseFile | null;
  onGoToReview: () => void;
  onGoToFindings: () => void;
}

export function CompliancePage({ caseFile, onGoToReview, onGoToFindings }: Props) {
  const [findings, setFindings] = useState<RequirementReport | null>(null);
  const sessionId = caseFile?.session_id ?? null;
  const fingerprint = caseFile?.updated_at ?? null;

  useEffect(() => {
    if (!sessionId) {
      setFindings(null);
      return;
    }
    let current = true;
    api
      .getFindings(sessionId)
      .then((next) => {
        if (current) setFindings(next);
      })
      // The rest of the page stands on its own without findings, so a
      // failure here must not take the classification down with it.
      .catch(() => {
        if (current) setFindings(null);
      });
    return () => {
      current = false;
    };
  }, [sessionId, fingerprint]);

  const result = caseFile ? normalizeClassification(caseFile.classification_result) : null;

  if (!caseFile || caseFile.conversation_stage !== "classified" || !result || !result.table_7_ref) {
    return (
      <div className="ds-compliance-page">
        <EmptyState
          title="Not classified yet"
          description="Finish the conversation on the Overview page so the building can be classified against NBCS Table 7 before compliance requirements can be shown."
        />
      </div>
    );
  }

  return (
    <div className="ds-compliance-page">
      {/* Surfaced here, not only on the Review page: this is where people
          come to read the classification, and a flagged case that nobody
          ever opens is the failure this phase exists to prevent. */}
      <ReviewBanner result={result} onGoToReview={onGoToReview} />

      <header className="ds-compliance-page__header">
        <h1>Compliance</h1>
        <p>What NBCS Part F requires for this building, based on its classification. Per-requirement pass/fail evaluation arrives in a later phase.</p>
      </header>

      <Card title="Classification rollup">
        <div className="ds-compliance-page__rollup">
          <StatusPill status={overallStatus(result)} />
          <div className="ds-compliance-page__rollup-facts">
            <span>Table 7 reference: <strong>{result.table_7_ref || "Not yet known"}</strong></span>
            {result.protection_level && <span>Protection level: <strong>{result.protection_level}</strong></span>}
            {result.is_high_rise !== null && <span>High rise: <strong>{result.is_high_rise ? "Yes" : "No"}</strong></span>}
          </div>
        </div>
        {result.applicable_state_checklist_id && (
          <p className="ds-compliance-page__checklist-note">
            A state-specific NOC checklist ({result.applicable_state_checklist_id}) may also apply — state checklists are a lower-priority,
            optional feature for now.
          </p>
        )}
      </Card>

      {/* Phase 4: the per-requirement verdicts. Before this every clause
          below rendered the same undifferentiated "unknown", because
          nothing evaluated whether the building met any of them. */}
      {findings && findings.evaluated && (
        <Card title="Requirement findings">
          <div className="ds-compliance-page__findings-head">
            <StatusPill
              status={findingsSummaryTone(findings.not_met_count, findings.unknown_count)}
              label={
                findings.not_met_count > 0
                  ? `${findings.not_met_count} not declared`
                  : findings.unknown_count > 0
                    ? `${findings.unknown_count} not known`
                    : "All required systems declared"
              }
            />
            <Button variant="secondary" size="sm" onClick={onGoToFindings}>
              See all findings
            </Button>
          </div>
          <table className="ds-compliance-page__table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Installation</th>
                <th>Recorded as</th>
              </tr>
            </thead>
            <tbody>
              {findings.findings
                .filter((finding) => finding.required)
                .map((finding) => (
                  <tr key={finding.code}>
                    <td>
                      <StatusPill status={findingTone(finding.status)} label={findingLabel(finding.status)} size="sm" />
                    </td>
                    <td>{finding.label}</td>
                    <td>{finding.matched_declaration ?? "—"}</td>
                  </tr>
                ))}
            </tbody>
          </table>
          <p className="ds-compliance-page__checklist-note">
            <strong>Declared, not verified.</strong> No installation has been inspected, and coverage, specification
            and design have not been checked.
          </p>
        </Card>
      )}

      <Card title="Applicable requirements">
        {result.applicable_clauses.length === 0 ? (
          <EmptyState title="No specific clauses identified" description="The classifier didn't attach any Table 7 clause references to this case." />
        ) : (
          <table className="ds-compliance-page__table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Clause</th>
                <th>Why it applies</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {result.applicable_clauses.map((clause) => (
                <tr key={clause}>
                  <td>
                    <StatusPill status={clauseStatus(result)} size="sm" />
                  </td>
                  <td>{clause}</td>
                  <td>Table 7 reference {result.table_7_ref || "—"}{result.protection_level ? `, ${result.protection_level}` : ""}</td>
                  <td>Confirm with a licensed fire consultant</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {result.notes.length > 0 && (
        <Card title="Notes">
          <ul className="ds-compliance-page__notes">
            {result.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </Card>
      )}

      <WhatIfPanel caseFile={caseFile} />
    </div>
  );
}
