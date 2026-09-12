import { Badge } from "../../design-system/components/Badge";
import { DocumentResultCard } from "../../design-system/components/DocumentResultCard";
import { StatusPill } from "../../design-system/components/StatusPill";
import type { ConversationEntry } from "./conversation";
import "./ConversationMessage.css";

interface Props {
  entry: ConversationEntry;
}

export function ConversationMessage({ entry }: Props) {
  if (entry.kind === "user") {
    return (
      <div className="ds-conv-row ds-conv-row--user">
        <div className="ds-conv-bubble ds-conv-bubble--user">{entry.text}</div>
      </div>
    );
  }

  if (entry.kind === "agent") {
    return (
      <div className="ds-conv-row ds-conv-row--agent">
        <div className="ds-conv-bubble ds-conv-bubble--agent">{entry.text}</div>
      </div>
    );
  }

  if (entry.kind === "system") {
    return (
      <div className="ds-conv-row ds-conv-row--system">
        <span className="ds-conv-system">{entry.text}</span>
      </div>
    );
  }

  if (entry.kind === "document-result") {
    return (
      <div className="ds-conv-row ds-conv-row--agent">
        <div className="ds-conv-row__wide">
          <DocumentResultCard fileName={entry.fileName} summary={entry.summary} />
        </div>
      </div>
    );
  }

  // classification-result
  const { result } = entry;
  return (
    <div className="ds-conv-row ds-conv-row--agent">
      <div className="ds-conv-card">
        <div className="ds-conv-card__header">
          <span className="ds-conv-card__title">Classification</span>
          {result.require_human_review_flag ? (
            <StatusPill status="human_review" />
          ) : (
            <StatusPill status="info" label="Complete" />
          )}
        </div>
        <div className="ds-conv-card__body">
          <dl className="ds-conv-card__grid">
            <dt>Part F applies</dt>
            <dd>{result.applies === null ? "Not yet determined" : result.applies ? "Yes" : "No"}</dd>
            {result.table_7_ref && (
              <>
                <dt>Table 7 reference</dt>
                <dd>{result.table_7_ref}</dd>
              </>
            )}
            {result.protection_level && (
              <>
                <dt>Protection level</dt>
                <dd>{result.protection_level}</dd>
              </>
            )}
            {result.is_high_rise !== null && (
              <>
                <dt>High rise</dt>
                <dd>{result.is_high_rise ? "Yes" : "No"}</dd>
              </>
            )}
          </dl>
          {result.applicable_clauses.length > 0 && (
            <div className="ds-conv-card__fields">
              {result.applicable_clauses.map((clause) => (
                <Badge key={clause}>{clause}</Badge>
              ))}
            </div>
          )}
          {result.notes.length > 0 && (
            <ul className="ds-conv-card__notes">
              {result.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
