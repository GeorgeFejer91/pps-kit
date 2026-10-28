import * as pretext from "@chenglou/pretext";
import { initializeBoundedText } from "../../../packages/pps-resources/assets/ui/bounded-text.mjs";

let typography;
let viewerTypography;
let viewerResize;

function measureViewerTypography() {
  viewerTypography?.disconnect();
  viewerResize?.disconnect();
  const frame = document.getElementById("trajectory-frame");
  const root = frame?.contentDocument?.body;
  if (root) {
    viewerTypography = initializeBoundedText(root, pretext, "#hud > *");
    const hud = root.querySelector("#hud");
    if (hud) {
      // The iframe has its own font settings. If enlarged HUD text no longer
      // fits, enlarge its outer preview cell instead of clipping or shrinking it.
      viewerResize = new ResizeObserver(() => {
        const box = hud.getBoundingClientRect();
        const height = `${Math.ceil(box.bottom + box.top + frame.clientTop * 2)}px`;
        if (frame.style.getPropertyValue("--trajectory-hud-min-height") !== height) frame.style.setProperty("--trajectory-hud-min-height", height);
      });
      viewerResize.observe(hud);
    }
  }
}

export function refreshDocumentationTypography() { typography?.refresh(); }

export function initializeDocumentationTypography() {
  typography?.disconnect();
  // The shared owner uses ResizeObserver and preserves the computed text size.
  typography = initializeBoundedText(document.body, pretext, [
    "[data-pretext-fit]", "[data-pretext]",
    ".decision-segment button:not(.noise-type-button)", ".decision-segment .field-row > label",
    ".decision-segment .status-label", ".decision-segment .bounded-select-value",
    ".rail-nav-group a > span", ".modal-card button", ".modal-card .field-row > label",
    ".site-tab", ".site-tab > span", ".brand-name", ".brand-subtitle", "#toast",
    ".bounded-select-option", ".bounded-select-value", ".status-label",
    "#native-execution button", "#native-execution label", "#native-execution summary",
    "[data-publication-network-root] button", "[data-publication-network-root] summary",
    "#publication-network-tooltip > *", ".publication-network-detail a",
    "#schedule-segment button", "#schedule-segment .status-label", "#schedule-segment td",
    "#run-segment button", "#run-segment .status-label", "#run-segment td",
    "#downloads-page .button-link",
  ].join(","));
  document.getElementById("trajectory-frame")?.addEventListener("load", measureViewerTypography);
  measureViewerTypography();
}
