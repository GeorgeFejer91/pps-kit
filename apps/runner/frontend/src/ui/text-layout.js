import * as pretext from "@chenglou/pretext";
import { initializeBoundedText } from "../../../../../packages/pps-resources/assets/ui/bounded-text.mjs";

export function initializeTextLayout() {
  return initializeBoundedText(document.body, pretext,
    "button, summary, .badge, .status-value, h2, .safety-copy, .subtle, .notice, [data-pretext]");
}
