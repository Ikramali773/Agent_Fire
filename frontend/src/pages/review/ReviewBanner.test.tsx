import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeCaseFile } from "../../test/fixtures";
import { normalizeClassification } from "../../lib/caseFileFields";
import { ReviewBanner } from "./ReviewBanner";

afterEach(cleanup);

function classification(overrides = {}) {
  return normalizeClassification({
    ...makeCaseFile().classification_result,
    ...overrides,
  });
}

describe("ReviewBanner", () => {
  it("shows nothing at all when the engine did not flag the case", () => {
    // A banner on every case is the same as a banner on none.
    const { container } = render(
      <ReviewBanner result={classification({ require_human_review_flag: false })} onGoToReview={vi.fn()} />,
    );

    expect(container.firstChild).toBeNull();
  });

  it("says WHY, using the engine's typed reasons", () => {
    render(
      <ReviewBanner
        result={classification({
          require_human_review_flag: true,
          review_reasons: [{ code: "not_permitted_combination", detail: "Long prose here." }],
        })}
        onGoToReview={vi.fn()}
      />,
    );

    expect(screen.getByText(/Occupancy combination not permitted/)).toBeTruthy();
  });

  it("lists every reason, not just the first", () => {
    render(
      <ReviewBanner
        result={classification({
          require_human_review_flag: true,
          review_reasons: [
            { code: "mandatory_occupancy", detail: "a" },
            { code: "no_band_matched", detail: "b" },
          ],
        })}
        onGoToReview={vi.fn()}
      />,
    );

    const text = screen.getByRole("note").textContent ?? "";
    expect(text).toContain("Occupancy always needs an expert");
    expect(text).toContain("No Table 7 band matched");
  });

  it("still explains itself when a flag arrives with no typed reason", () => {
    // Defensive: a case file classified before typed reasons existed.
    render(
      <ReviewBanner
        result={classification({ require_human_review_flag: true, review_reasons: [] })}
        onGoToReview={vi.fn()}
      />,
    );

    expect(screen.getByText(/could not complete this case/)).toBeTruthy();
  });

  it("takes the user to the review queue", async () => {
    const onGoToReview = vi.fn();
    render(
      <ReviewBanner
        result={classification({ require_human_review_flag: true })}
        onGoToReview={onGoToReview}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Open review" }));

    expect(onGoToReview).toHaveBeenCalled();
  });
});
