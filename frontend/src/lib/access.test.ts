import { describe, expect, it } from "vitest";
import { makeCaseFile } from "../test/fixtures";
import { canEditCaseFile, isReadOnlyCaseFile } from "./access";
import type { User } from "../types";

const OWNER: User = { id: "u1", email: "owner@example.com", created_at: "2026-01-01T00:00:00Z" };
const REVIEWER: User = { id: "u2", email: "reviewer@example.com", created_at: "2026-01-01T00:00:00Z" };

describe("canEditCaseFile", () => {
  it("lets anyone edit an anonymous case file", () => {
    // Phase 1's model: no owner means open to whoever holds the session
    // id. Phase 3 must not have quietly narrowed that.
    expect(canEditCaseFile(makeCaseFile({ owner_user_id: null }), null)).toBe(true);
    expect(canEditCaseFile(makeCaseFile({ owner_user_id: null }), REVIEWER)).toBe(true);
  });

  it("lets the owner edit their own project", () => {
    expect(canEditCaseFile(makeCaseFile({ owner_user_id: "u1" }), OWNER)).toBe(true);
  });

  it("does not let a reviewer edit someone else's project", () => {
    // A verdict on facts the reviewer could have changed is worth nothing.
    expect(canEditCaseFile(makeCaseFile({ owner_user_id: "u1" }), REVIEWER)).toBe(false);
  });

  it("does not let a signed-out visitor edit an owned project", () => {
    expect(canEditCaseFile(makeCaseFile({ owner_user_id: "u1" }), null)).toBe(false);
  });

  it("treats 'no case file yet' as editable, so a draft is not disabled", () => {
    expect(canEditCaseFile(null, null)).toBe(true);
  });
});

describe("isReadOnlyCaseFile", () => {
  it("is the inverse, except that no case file is never read-only", () => {
    expect(isReadOnlyCaseFile(null, null)).toBe(false);
    expect(isReadOnlyCaseFile(makeCaseFile({ owner_user_id: "u1" }), REVIEWER)).toBe(true);
    expect(isReadOnlyCaseFile(makeCaseFile({ owner_user_id: "u1" }), OWNER)).toBe(false);
  });
});
