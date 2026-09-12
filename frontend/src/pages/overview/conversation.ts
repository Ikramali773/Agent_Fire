import type { ClassificationResult, IngestSummary } from "../../types";

// The Overview page's own presentation model for one turn of the
// conversation. Distinct from the wire-level ChatMessage type: this adds
// the "what kind of thing just happened" tag (plain reply, document
// result, classification result, system notice) so each renders with the
// right visual treatment - see the design brief's "distinct visual
// treatment per message type" requirement. Purely a presentation layer
// over the same api.* responses; no new business logic.
export type ConversationEntry =
  | { kind: "user"; id: string; text: string }
  | { kind: "agent"; id: string; text: string }
  | { kind: "document-result"; id: string; fileName: string; summary: IngestSummary }
  | { kind: "classification-result"; id: string; result: ClassificationResult }
  | { kind: "system"; id: string; text: string };

let counter = 0;
export function nextEntryId(): string {
  counter += 1;
  return `entry-${counter}`;
}
