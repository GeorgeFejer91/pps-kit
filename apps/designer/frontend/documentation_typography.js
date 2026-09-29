import * as pretext from "@chenglou/pretext";
import { initializeBoundedText } from "../../../packages/pps-resources/assets/ui/bounded-text.mjs";

let typography;

export function refreshDocumentationTypography() { typography?.refresh(); }

export function initializeDocumentationTypography() {
  typography?.disconnect();
  // The shared owner uses ResizeObserver and preserves the computed text size.
  typography = initializeBoundedText(document.body, pretext, [
    "[data-pretext-fit]", "[data-pretext]",
    ".segment-heading h2", ".segment-heading .segment-kicker",
    ".segment-heading .segment-info-button", ".segment-heading .segment-reopen-button",
    "#schedule-segment button", "#schedule-segment .status-label", "#schedule-segment td",
    "#run-segment button", "#run-segment .status-label", "#run-segment td",
  ].join(","));
}
