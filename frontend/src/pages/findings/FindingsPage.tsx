import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import { Card } from "../../design-system/components/Card";
import { EmptyState } from "../../design-system/components/EmptyState";
import { StatusPill } from "../../design-system/components/StatusPill";
import { findingLabel, findingsSummaryTone, findingTone } from "../../lib/findings";
import type { CaseFile, OccupantLoadEstimate, RequirementReport } from "../../types";
import "./FindingsPage.css";

interface Props {
  caseFile: CaseFile | null;
}

// Phase 4's compliance engine, on screen. Phase 1's classifier determines
// WHICH requirements apply; until this existed nothing determined whether
// the building met them, which is why every clause on the Compliance page
// read "unknown".
//
// The wording throughout says "declared", never "verified" or "compliant".
// The system knows an installation was reported; it does not know that it
// exists, covers the right areas, or is correctly designed. Blurring that
// would make the product assert compliance it has not established.
export function FindingsPage({ caseFile }: Props) {
  const [report, setReport] = useState<RequirementReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sessionId = caseFile?.session_id ?? null;
  // Re-fetched when the case file changes: findings are derived from it, so
  // an edit anywhere must be reflected here without a reclassify step.
  const fingerprint = caseFile?.updated_at ?? null;

  useEffect(() => {
    if (!sessionId) {
      setReport(null);
      return;
    }
    let current = true;
    setError(null);
    api
      .getFindings(sessionId)
      .then((next) => {
        if (current) setReport(next);
      })
      .catch((err) => {
        if (current)
          setError(err instanceof ApiError ? `Could not load findings (${err.status}).` : "Could not load findings.");
      });
    return () => {
      current = false;
    };
  }, [sessionId, fingerprint]);

  if (!caseFile) {
    return (
      <div className="ds-findings-page">
        <EmptyState
          title="No active case yet"
          description="Start a conversation on the Overview page. Findings appear once the building has been classified against a Table 7 band."
        />
      </div>
    );
  }

  if (error) {
    return (
      <div className="ds-findings-page">
        <p className="ds-findings-page__note ds-findings-page__note--error" role="alert">
          {error}
        </p>
      </div>
    );
  }

  if (!report) return <div className="ds-findings-page"><p className="ds-findings-page__note">Loading findings…</p></div>;

  if (!report.evaluated) {
    return (
      <div className="ds-findings-page">
        <EmptyState
          title="Nothing to evaluate yet"
          description="This building hasn't been classified against a Table 7 band, so no specific requirement applies to it. Finish the conversation on the Overview page first."
        />
        {/* An occupant load needs only an occupancy and an area, not a
            Table 7 band - so it is answerable here, and this is precisely
            the state where it is the only thing that can be said. The
            backend computes it on this path for that reason; discarding it
            would hide a figure that is already known. */}
        <OccupantLoadCard load={report.occupant_load} />
      </div>
    );
  }

  const required = report.findings.filter((finding) => finding.required);
  const notRequired = report.findings.filter((finding) => !finding.required);

  return (
    <div className="ds-findings-page">
      <header className="ds-findings-page__header">
        <h1>Findings</h1>
        <p>
          Each installation Table {report.table_7_ref}
          {report.protection_level ? ` band ${report.protection_level}` : ""} requires, against what has been recorded
          for this building.
        </p>
      </header>

      <Card title="Summary">
        <div className="ds-findings-page__summary">
          <StatusPill
            status={findingsSummaryTone(report.not_met_count, report.unknown_count)}
            label={
              report.not_met_count > 0
                ? `${report.not_met_count} not declared`
                : report.unknown_count > 0
                  ? `${report.unknown_count} not known`
                  : "All required systems declared"
            }
          />
          <span className="ds-findings-page__counts">
            {report.met_count} declared · {report.not_met_count} not declared · {report.unknown_count} not known ·{" "}
            {required.length} required in total
          </span>
        </div>
        <p className="ds-findings-page__caveat">
          <strong>Declared, not verified.</strong> These statuses come from what has been recorded about this building.
          No installation has been inspected, and coverage, specification and design have not been checked — that needs
          the plans, and a licensed fire consultant.
        </p>
      </Card>

      <OccupantLoadCard load={report.occupant_load} />

      <Card title="Required for this building" padded={false}>
        <ul className="ds-findings-page__list">
          {required.map((finding) => (
            <li key={finding.code} className="ds-findings-page__row">
              <div className="ds-findings-page__row-head">
                <span className="ds-findings-page__name">{finding.label}</span>
                <StatusPill status={findingTone(finding.status)} label={findingLabel(finding.status)} size="sm" />
              </div>
              <p className="ds-findings-page__detail">{finding.detail}</p>
              {finding.matched_declaration && (
                <p className="ds-findings-page__evidence">
                  Matched to what was recorded: “{finding.matched_declaration}”
                </p>
              )}
            </li>
          ))}
        </ul>
      </Card>

      {report.unrecognized_declarations.length > 0 && (
        <Card title="Recorded but not recognised">
          <p className="ds-findings-page__caveat">
            These were recorded for this building but don't match any installation Table 7 scores, so they have not
            been counted either way. A system we didn't recognise is not the same as a system you don't have.
          </p>
          <ul className="ds-findings-page__plain-list">
            {report.unrecognized_declarations.map((declaration) => (
              <li key={declaration}>{declaration}</li>
            ))}
          </ul>
        </Card>
      )}

      {notRequired.length > 0 && (
        <Card title="Not required for this building" padded={false}>
          <ul className="ds-findings-page__list">
            {notRequired.map((finding) => (
              <li key={finding.code} className="ds-findings-page__row ds-findings-page__row--muted">
                <div className="ds-findings-page__row-head">
                  <span className="ds-findings-page__name">{finding.label}</span>
                  <StatusPill status="info" label="Not required" size="sm" />
                </div>
                {finding.matched_declaration && (
                  <p className="ds-findings-page__evidence">Recorded anyway: “{finding.matched_declaration}”</p>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

// Kept out of the findings list on purpose: a finding carries a status,
// and an occupant load has none - it is a head count, not a verdict, and
// listing it among verdicts would invite it being read as one.
function OccupantLoadCard({ load }: { load: OccupantLoadEstimate | null }) {
  if (!load) return null;
  return (
    <Card title="Occupant load">
      <p className="ds-findings-page__occupants">
        {load.resolved
          ? `${load.people} people`
          : load.low !== null
            ? `Between ${load.low} and ${load.high} people`
            : "Not derivable from floor area"}
      </p>
      <p className="ds-findings-page__caveat">{load.explanation}</p>
      {load.caveats.map((caveat) => (
        <p className="ds-findings-page__caveat" key={caveat}>
          {caveat}
        </p>
      ))}
    </Card>
  );
}
