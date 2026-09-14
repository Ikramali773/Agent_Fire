import { describe, expect, it } from "vitest";
import { readLinkToken } from "./linkToken";

describe("readLinkToken", () => {
  it("reads a reset token", () => {
    expect(readLinkToken("?reset=abc123")).toEqual({ kind: "reset", token: "abc123" });
  });

  it("reads an invite token", () => {
    expect(readLinkToken("?invite=xyz")).toEqual({ kind: "invite", token: "xyz" });
  });

  it("ignores an empty or whitespace-only token", () => {
    // A link that got truncated somewhere must land in the ordinary app,
    // not in a reset form with nothing behind it.
    expect(readLinkToken("?reset=")).toBeNull();
    expect(readLinkToken("?invite=%20%20")).toBeNull();
  });

  it("ignores unrelated query strings", () => {
    expect(readLinkToken("?utm_source=email")).toBeNull();
    expect(readLinkToken("")).toBeNull();
  });

  it("takes reset first when a URL somehow carries both", () => {
    // Shouldn't happen, but landing on a password reset is the safer of
    // the two: it asks for a credential rather than granting access.
    expect(readLinkToken("?invite=i&reset=r")).toEqual({ kind: "reset", token: "r" });
  });
});
