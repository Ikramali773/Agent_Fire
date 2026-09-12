import { Card } from "../../design-system/components/Card";
import { EmptyState } from "../../design-system/components/EmptyState";
import { StatusPill } from "../../design-system/components/StatusPill";
import { normalizeClassification } from "../../lib/caseFileFields";
import type { CaseFile } from "../../types";
import { clauseStatus, overallStatus } from "./complianceStatus";
import "./CompliancePage.css";

interface Props {
  caseFile: CaseFile | null;
}

export function CompliancePage({ caseFile }: Props) {
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
    </div>
  );
}
