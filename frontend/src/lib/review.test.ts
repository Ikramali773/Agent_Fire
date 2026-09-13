import { describe, expect, it } from "vitest";
import { RECORDABLE_STATUSES, reviewReasonLabel, reviewStatusLabel, reviewStatusTone } from "./review";

describe("reviewReasonLabel", () => {
  it("phrases a reason for a person rather than naming the enum", () => {
    expect(reviewReasonLabel("not_permitted_combination")).toBe("Occupancy combination not permitted");
  });

  it("falls back to the code rather than rendering nothing", () => {
    // A newer backend against an older frontend must still show something.
    expect(reviewReasonLabel("some_future_reason")).toBe("some_future_reason");
  });
});

describe("reviewStatusTone", () => {
  it("does not present an approval as a compliance pass", () => {
    // Load-bearing: this product does not certify anything, and the
    // footer on every page says so. "Approved" means a named person
    // signed off, not that the system asserts compliance.
    expect(reviewStatusTone("approved")).not.toBe("pass");
    expect(reviewStatusTone("approved")).toBe("info");
  });

  it("keeps an unreviewed case in the human-review tone", () => {
    expect(reviewStatusTone("needs_review")).toBe("human_review");
  });

  it("treats a rejection as a failure", () => {
    expect(reviewStatusTone("rejected")).toBe("fail");
  });

  it("falls back to unknown for a status it has never seen", () => {
    expect(reviewStatusTone("something_new")).toBe("unknown");
  });
});

describe("reviewStatusLabel", () => {
  it("labels every recordable status", () => {
    for (const status of RECORDABLE_STATUSES) {
      expect(reviewStatusLabel(status)).not.toBe(status);
    }
  });

  it("labels the derived starting status", () => {
    expect(reviewStatusLabel("needs_review")).toBe("Needs review");
  });
});

describe("RECORDABLE_STATUSES", () => {
  it("never offers needs_review as a verdict", () => {
    // It is derived from "no events yet" - offering it would let a review
    // be silently rewound, and the backend rejects it with a 422 anyway.
    expect(RECORDABLE_STATUSES).not.toContain("needs_review");
  });
});
