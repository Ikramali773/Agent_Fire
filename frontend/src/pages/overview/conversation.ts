import { normalizeClassification } from "../../lib/caseFileFields";
import type { CaseFile, ClassificationResult, ConversationMessage, IngestSummary } from "../../types";

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
  | { kind: "document-uploading"; id: string; fileName: string }
  | { kind: "document-result"; id: string; fileName: string; summary: IngestSummary }
  | { kind: "classification-result"; id: string; result: ClassificationResult }
  | { kind: "system"; id: string; text: string };

let counter = 0;
export function nextEntryId(): string {
  counter += 1;
  return `entry-${counter}`;
}

// Rebuilds the on-screen conversation from the persisted transcript
// (GET /case-files/{id}/messages), so leaving the Overview page and coming
// back - or reopening a project from Project History - restores what was
// actually said, cards and all, not just plain text. The server stores the
// message `kind` precisely so this mapping never has to guess.
export function toConversationEntries(messages: ConversationMessage[]): ConversationEntry[] {
  return messages.map((message): ConversationEntry => {
    const id = `msg-${message.id}`;

    if (message.kind === "document_result") {
      const payload = (message.payload ?? {}) as { file_name?: string; summary?: IngestSummary };
      return {
        kind: "document-result",
        id,
        fileName: payload.file_name ?? "Uploaded document",
        summary: payload.summary as IngestSummary,
      };
    }

    if (message.kind === "classification_result") {
      return {
        kind: "classification-result",
        id,
        result: normalizeClassification(message.payload as CaseFile["classification_result"]),
      };
    }

    if (message.role === "user") return { kind: "user", id, text: message.text };
    if (message.role === "system") return { kind: "system", id, text: message.text };
    return { kind: "agent", id, text: message.text };
  });
}
