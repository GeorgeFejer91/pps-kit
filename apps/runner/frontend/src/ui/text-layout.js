import * as pretext from "@chenglou/pretext";
import { initializeBoundedText } from "../../../../../packages/pps-resources/assets/ui/bounded-text.mjs";

export function initializeTextLayout() {
  return initializeBoundedText(document.body, pretext,
    "button, summary, label, .badge, .status-chip strong, .status-chip span, .connection-pill, h1, h2, h3, dt, dd, .safety-copy, .subtle, .timeline-event, .timeline-labels span, .notice, .toast, .layout-status, [data-pretext]");
}

// Presentation only: navigation never invokes a runner action or moves controls.
export function initializeWorkspaceLayout() {
  const shell = document.querySelector(".app-shell");
  if (!shell) return;
  const status = document.getElementById("layout-status");
  let frame = 0;
  for (const deck of document.querySelectorAll("[data-workspace-deck]")) {
    const views = [...deck.querySelectorAll(":scope > [data-workspace]")];
    const navigation = document.createElement("nav");
    navigation.className = "workspace-navigation";
    navigation.setAttribute("aria-label", deck.getAttribute("aria-label"));
    const buttons = views.map((view, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "workspace-button";
      button.textContent = view.dataset.workspaceLabel;
      button.dataset.workspaceOpen = view.dataset.workspace;
      button.setAttribute("aria-controls", view.id);
      if (index === 0) button.setAttribute("aria-current", "page");
      view.hidden = index !== 0;
      button.addEventListener("click", () => {
        for (const candidate of buttons) {
          if (candidate === button) candidate.setAttribute("aria-current", "page");
          else candidate.removeAttribute("aria-current");
        }
        for (const candidate of views) candidate.hidden = candidate !== view;
        refresh();
      });
      return button;
    });
    navigation.append(...buttons);
    deck.prepend(navigation);
  }
  for (const link of document.querySelectorAll("[data-workspace-link]")) link.addEventListener("click", () => {
    const view = document.getElementById(`workspace-${link.dataset.workspaceLink}`);
    const route = view?.closest("[data-panel]")?.dataset.panel;
    document.querySelector(`[data-tab="${route}"]`)?.click();
    document.querySelector(`[data-workspace-open="${link.dataset.workspaceLink}"]`)?.click();
  });

  function refresh() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(measure);
  }
  function measure() {
    // Try the definite shell again after each real resize/content change so an
    // expanded window recovers stretch. Never reduce the user's type to fit.
    const scale = shell.getBoundingClientRect().width / shell.offsetWidth || 1;
    const supported = innerWidth / scale >= 1120 && innerHeight / scale >= 768;
    shell.dataset.layout = supported ? "stretch" : "flow";
    status.hidden = true;
    const nodes = [shell, ...shell.querySelectorAll("main, .tab-panel.is-active, .tab-panel.is-active .workspace-view:not([hidden]), .tab-panel.is-active .panel")]
      .filter(node => node.getClientRects().length);
    const overflow = supported && nodes.some(node => node.scrollHeight > node.clientHeight + 2
      || node.scrollWidth > node.clientWidth + 2);
    if (!supported || overflow) {
      shell.dataset.layout = "flow";
      status.textContent = overflow
        ? "Expanded text or details need more room. This view uses document scrolling; all controls and values remain available."
        : "Compact layout: controls reflow in reading order. Scroll the page to reach all details.";
      status.hidden = false;
    }
  }
  const mutation = new MutationObserver(refresh);
  // Our own status writes must not continually schedule a new measurement.
  mutation.observe(shell.querySelector("main"), { subtree: true, childList: true, characterData: true,
    attributes: true, attributeFilter: ["hidden", "open", "class"] });
  const sizes = new WeakMap();
  const resize = new ResizeObserver(entries => {
    for (const entry of entries) {
      const next = `${entry.contentRect.width}:${entry.contentRect.height}`;
      if (next !== sizes.get(entry.target)) { sizes.set(entry.target, next); refresh(); }
    }
  });
  for (const node of [document.documentElement, shell.querySelector(".topbar"), ...shell.querySelectorAll(".panel")]) resize.observe(node);
  window.addEventListener("resize", refresh);
  document.fonts?.addEventListener("loadingdone", refresh);
  Promise.resolve(document.fonts?.ready).then(refresh);
}

// A local page over the existing complete DOM collection. The data owner still
// retains every row, and a changed collection resets its page rather than hiding
// a newly selected target or replacement package behind an obsolete page index.
export function paginateCollection(list, { size = 4, previous, next, label } = {}) {
  let page = 0, identities = "", selection = null;
  if (!previous) {
    const navigation = document.createElement("div");
    navigation.className = "inline-actions collection-navigation";
    previous = document.createElement("button");
    next = document.createElement("button");
    label = document.createElement("span");
    for (const [button, text] of [[previous, "Previous targets"], [next, "Next targets"]]) {
      button.type = "button"; button.className = "button"; button.textContent = text;
    }
    label.setAttribute("role", "status");
    navigation.append(previous, label, next);
    list.after(navigation);
  }
  function render() {
    const items = [...list.children].filter(node => node.matches("li, button"));
    page = Math.min(page, Math.max(0, Math.ceil(items.length / size) - 1));
    items.forEach((item, index) => { item.hidden = index < page * size || index >= (page + 1) * size; });
    previous.disabled = page === 0;
    next.disabled = (page + 1) * size >= items.length;
    label.textContent = items.length ? `${page * size + 1}–${Math.min((page + 1) * size, items.length)} of ${items.length}` : "No entries";
    previous.parentElement.hidden = items.length <= size;
  }
  previous.addEventListener("click", () => { if (!previous.disabled) { page--; render(); } });
  next.addEventListener("click", () => { if (!next.disabled) { page++; render(); } });
  new MutationObserver(() => {
    const items = [...list.children].filter(node => node.matches("li, button"));
    const keys = items.map(node => node.dataset.streamId ?? node.textContent);
    const nextIdentities = JSON.stringify(keys);
    const selected = items.findIndex(node => node.getAttribute("aria-pressed") === "true");
    const nextSelection = selected < 0 ? null : keys[selected];
    if (nextIdentities !== identities) page = 0;
    if (nextSelection !== selection && selected >= 0) page = Math.floor(selected / size);
    identities = nextIdentities;
    selection = nextSelection;
    render();
  }).observe(list, { childList: true });
  render();
}
