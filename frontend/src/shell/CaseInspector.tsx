import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { Card } from "../design-system/components/Card";
import { DataRow } from "../design-system/components/DataRow";
import { EmptyState } from "../design-system/components/EmptyState";
import { StatusPill } from "../design-system/components/StatusPill";
import { fieldMeta, formatLabel, formatValue } from "../lib/caseFileFields";
import type { CaseFile } from "../types";
import "./CaseInspector.css";

interface Props {
  caseFile: CaseFile | null;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

export function CaseInspector({ caseFile, collapsed, onToggleCollapsed }: Props) {
  return (
    <aside className={`ds-case-inspector${collapsed ? " ds-case-inspector--collapsed" : ""}`} aria-label="Case context">
      <div className="ds-case-inspector__header">
        {!collapsed && <span className="ds-case-inspector__title">Case File</span>}
        <button
          type="button"
          className="ds-case-inspector__toggle"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? "Expand case inspector" : "Collapse case inspector"}
        >
          {collapsed ? <PanelRightOpen aria-hidden="true" /> : <PanelRightClose aria-hidden="true" />}
        </button>
      </div>

      {!collapsed && (
        <div className="ds-case-inspector__body">
          {!caseFile ? (
            <EmptyState title="No active case yet" description="Start a conversation on the Overview page to begin building the case file." />
          ) : (
            <CaseInspectorContent caseFile={caseFile} />
          )}
        </div>
      )}
    </aside>
  );
}

function CaseInspectorContent({ caseFile }: { caseFile: CaseFile }) {
  const sources = caseFile.field_sources ?? {};
  const sourceCounts = { user: 0, document: 0, inferred: 0, unknown: 0 };
  for (const entry of Object.values(sources)) {
    if (entry.source in sourceCounts) sourceCounts[entry.source as keyof typeof sourceCounts] += 1;
  }
  const classification = caseFile.classification_result;

  return (
    <>
      <Card title="Project" padded={false}>
        <DataRow compact label="Name" value={formatValue(caseFile.project_name)} {...fieldMeta(caseFile, "project_name")} />
        <DataRow compact label="State" value={formatValue(caseFile.state)} {...fieldMeta(caseFile, "state")} />
        <DataRow compact label="City" value={formatValue(caseFile.city)} {...fieldMeta(caseFile, "city")} />
        <DataRow compact label="Project stage" value={formatLabel(caseFile.project_stage)} {...fieldMeta(caseFile, "project_stage")} />
        <DataRow compact label="Goal" value={formatLabel(caseFile.goal)} {...fieldMeta(caseFile, "goal")} />
        <DataRow compact label="Code edition" value={caseFile.code_edition === "2026" ? "NBCS 2026" : "NBC 2016"} />
      </Card>

      <Card title="Classification" padded={false}>
        <DataRow compact label="Occupancy type" value={formatValue(caseFile.occupancy_type)} {...fieldMeta(caseFile, "occupancy_type")} />
        <DataRow
          compact
          label="Subdivision"
          value={formatValue(caseFile.occupancy_subdivision)}
          {...fieldMeta(caseFile, "occupancy_subdivision")}
        />
        <DataRow compact label="Mixed occupancy" value={caseFile.mixed_occupancy ? "Yes" : "No"} {...fieldMeta(caseFile, "mixed_occupancy")} />
        <DataRow
          compact
          label="Hazard band"
          value={formatValue(caseFile.industrial_hazard_band)}
          {...fieldMeta(caseFile, "industrial_hazard_band")}
        />
        <DataRow compact label="Table 7 ref" value={formatValue(classification?.table_7_ref)} />
        <DataRow compact label="Protection level" value={formatValue(classification?.protection_level)} />
        {classification?.require_human_review_flag && (
          <div className="ds-case-inspector__flag">
            <StatusPill status="human_review" size="sm" />
          </div>
        )}
      </Card>

      <Card title="Building" padded={false}>
        <DataRow compact label="Height (m)" value={formatValue(caseFile.height_m)} {...fieldMeta(caseFile, "height_m")} />
        <DataRow compact label="High rise" value={formatValue(caseFile.is_high_rise)} {...fieldMeta(caseFile, "is_high_rise")} />
        <DataRow
          compact
          label="Floors above ground"
          value={formatValue(caseFile.floors_above_ground)}
          {...fieldMeta(caseFile, "floors_above_ground")}
        />
        <DataRow
          compact
          label="Floors below ground"
          value={formatValue(caseFile.floors_below_ground)}
          {...fieldMeta(caseFile, "floors_below_ground")}
        />
        <DataRow
          compact
          label="Built-up area (sqm)"
          value={formatValue(caseFile.built_up_area_sqm)}
          {...fieldMeta(caseFile, "built_up_area_sqm")}
        />
        <DataRow compact label="Kitchens" value={formatValue(caseFile.kitchen_count)} {...fieldMeta(caseFile, "kitchen_count")} />
        <DataRow compact label="Doors" value={formatValue(caseFile.door_count)} {...fieldMeta(caseFile, "door_count")} />
      </Card>

      <Card title="Egress" padded={false}>
        <DataRow
          compact
          label="Staircases"
          value={formatValue(caseFile.number_of_staircases)}
          {...fieldMeta(caseFile, "number_of_staircases")}
        />
        <DataRow compact label="Exits" value={formatValue(caseFile.number_of_exits)} {...fieldMeta(caseFile, "number_of_exits")} />
      </Card>

      <Card title="Fire systems" padded={false}>
        <DataRow
          compact
          label="Existing systems"
          value={formatValue(caseFile.existing_fire_systems)}
          {...fieldMeta(caseFile, "existing_fire_systems")}
        />
      </Card>

      <Card title="Source & confidence">
        <p className="ds-case-inspector__rollup-note">
          Every field above carries where it came from. This is the rollup across all known fields.
        </p>
        <div className="ds-case-inspector__rollup">
          <span>Confirmed by you</span>
          <span className="tabular-nums">{sourceCounts.user}</span>
        </div>
        <div className="ds-case-inspector__rollup">
          <span>From a document</span>
          <span className="tabular-nums">{sourceCounts.document}</span>
        </div>
        <div className="ds-case-inspector__rollup">
          <span>Inferred</span>
          <span className="tabular-nums">{sourceCounts.inferred}</span>
        </div>
        <div className="ds-case-inspector__rollup">
          <span>Not yet known</span>
          <span className="tabular-nums">{sourceCounts.unknown}</span>
        </div>
      </Card>
    </>
  );
}
