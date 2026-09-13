import { describe, expect, it } from "vitest";
import { makeMessage } from "../../test/fixtures";
import { toConversationEntries } from "./conversation";

// Restoring a transcript is the whole reason messages are persisted with a
// `kind`: a reloaded conversation has to re-render the same cards the user
// saw live, not flatten them to text.
describe("toConversationEntries", () => {
  it("maps user, agent and system roles to their own entry kinds", () => {
    const entries = toConversationEntries([
      makeMessage({ id: 1, role: "agent", text: "Which state?" }),
      makeMessage({ id: 2, role: "user", text: "Gujarat" }),
      makeMessage({ id: 3, role: "system", text: "Document uploaded" }),
    ]);

    expect(entries.map((entry) => entry.kind)).toEqual(["agent", "user", "system"]);
  });

  it("keeps the server's order", () => {
    const entries = toConversationEntries([
      makeMessage({ id: 7, role: "user", text: "first" }),
      makeMessage({ id: 8, role: "agent", text: "second" }),
    ]);

    expect(entries.map((entry) => ("text" in entry ? entry.text : ""))).toEqual(["first", "second"]);
  });

  it("gives every entry a stable id derived from the message id", () => {
    // Not a running counter: re-rendering a restored transcript must not
    // hand React a different key for the same message.
    const first = toConversationEntries([makeMessage({ id: 42 })]);
    const second = toConversationEntries([makeMessage({ id: 42 })]);

    expect(first[0].id).toBe("msg-42");
    expect(second[0].id).toBe(first[0].id);
  });

  it("rebuilds a document result card from its payload", () => {
    const summary = {
      tier_used: 1,
      confidence: 0.92,
      needs_human_review: false,
      fields_extracted: ["height_m"],
      failure_reason: null,
      fact_extraction_skipped_reason: null,
    };

    const [entry] = toConversationEntries([
      makeMessage({ id: 5, kind: "document_result", text: "", payload: { file_name: "plan.pdf", summary } }),
    ]);

    expect(entry).toEqual({ kind: "document-result", id: "msg-5", fileName: "plan.pdf", summary });
  });

  it("names an unlabelled document rather than rendering an empty card", () => {
    const [entry] = toConversationEntries([makeMessage({ id: 6, kind: "document_result", text: "", payload: {} })]);

    expect(entry).toMatchObject({ kind: "document-result", fileName: "Uploaded document" });
  });

  it("rebuilds a classification card, normalizing the payload's optional fields", () => {
    const [entry] = toConversationEntries([
      makeMessage({
        id: 9,
        kind: "classification_result",
        text: "",
        payload: { applies: true, table_7_ref: "Table 7A", require_human_review_flag: false },
      }),
    ]);

    expect(entry.kind).toBe("classification-result");
    if (entry.kind !== "classification-result") throw new Error("expected a classification entry");
    expect(entry.result.table_7_ref).toBe("Table 7A");
    // The payload omitted these; the card maps over them unconditionally.
    expect(entry.result.applicable_clauses).toEqual([]);
    expect(entry.result.notes).toEqual([]);
  });

  it("treats a structured message's kind as authoritative over its role", () => {
    // An agent-role document_result must still render as a card.
    const [entry] = toConversationEntries([
      makeMessage({ id: 10, role: "agent", kind: "document_result", payload: { file_name: "a.pdf" } }),
    ]);

    expect(entry.kind).toBe("document-result");
  });

  it("returns nothing for an empty transcript", () => {
    expect(toConversationEntries([])).toEqual([]);
  });
});
