import { Check, Loader2 } from "lucide-react";
import "./ProgressSteps.css";

export interface ProgressStep {
  key: string;
  label: string;
}

interface Props {
  steps: ProgressStep[];
  /** Index of the step currently in progress. Steps before it are done. */
  activeIndex: number;
  /** Set when the active step has failed instead of completing. */
  failed?: boolean;
}

// Staged loading state - e.g. document processing: Uploaded -> Reading ->
// Extracting -> Checking confidence -> Ready. Never a generic spinner for
// anything that has real, nameable stages.
export function ProgressSteps({ steps, activeIndex, failed }: Props) {
  return (
    <ol className="ds-progress-steps">
      {steps.map((step, index) => {
        let state: "done" | "active" | "failed" | "pending" = "pending";
        if (index < activeIndex) state = "done";
        else if (index === activeIndex) state = failed ? "failed" : "active";

        return (
          <li key={step.key} className={`ds-progress-steps__item ds-progress-steps__item--${state}`}>
            <span className="ds-progress-steps__marker" aria-hidden="true">
              {state === "done" && <Check />}
              {state === "active" && <Loader2 className="ds-progress-steps__spin" />}
              {state === "failed" && "!"}
              {state === "pending" && <span className="ds-progress-steps__dot" />}
            </span>
            <span className="ds-progress-steps__label">{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
