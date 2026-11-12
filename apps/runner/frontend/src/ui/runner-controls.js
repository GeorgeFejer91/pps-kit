const SVG_NS = "http://www.w3.org/2000/svg";
const icons = {
  send: "m9 10 4-4 5 5-4 4zm-4 4 4-4 2 2-4 4zm10-10 2-2 4 4-2 2zm-6 8-2 2m8-8 2-2m-2 10 2 2m-5 2a4 4 0 0 0 6 0m-8 2a7 7 0 0 0 10 0",
  scan: "M3 8V4h4m10 0h4v4m0 8v4h-4m-10 0H3v-4m1-4h16M8 8a6 6 0 0 1 8 0M8 16a6 6 0 0 0 8 0",
  remote: "M6 2h8a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm2 5h4m-4 4h4m-3 7h2m7-13c1 1 1 3 0 4m2-6c2 2 2 6 0 8",
  study: "M6 5h12a2 2 0 0 1 2 2v13H4V7a2 2 0 0 1 2-2Zm3-2h6v4H9zm-1 9h8m-8 4h6",
  audio: "M3 9h4l5-4v14l-5-4H3zm13-1a5 5 0 0 1 0 8m2-11a9 9 0 0 1 0 14",
  note: "M5 3h14v13l-5 5H5zm9 18v-5h5M8 8h8m-8 4h5",
  refresh: "M20 7v5h-5M4 17v-5h5m-4-4a8 8 0 0 1 13-3l2 2M4 17l2 2a8 8 0 0 0 13-3",
  close: "m6 6 12 12M18 6 6 18",
  play: "M8 5v14l11-7z",
  next: "m9 5 7 7-7 7m7-7H4",
  pause: "M7 5h3v14H7zm7 0h3v14h-3z",
  stop: "M6 6h12v12H6z",
  abort: "M8 3h8l5 5v8l-5 5H8l-5-5V8zm4 4v6m0 4h.01",
  arm: "m13 2-8 12h6l-1 8 9-12h-6z",
  disarm: "M4 4l16 16M10 6l3-4v7m4 1h2l-4 6m-4-4-1 10 3-4m-5-9-3 5h6",
  response: "M9 12V5a2 2 0 0 1 4 0v5l5 1v5l-3 5h-5l-5-6a2 2 0 0 1 3-2l1 1",
  check: "m5 12 4 4L19 6",
  folder: "M3 6h7l2 2h9v11H3z",
  timeline: "M3 6h18M3 12h18M3 18h18M8 4v4m7 2v4m3 2v4",
  disconnect: "M8 3v5m8-5v5m-11 0h14l-2 7-5 3-5-3zm7 10v3",
  copy: "M8 8h12v12H8zM4 16V4h12",
  download: "M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4",
};

export function bindRunnerControls() {
  for (const button of document.querySelectorAll("button[data-icon]")) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", icons[button.dataset.icon]);
    svg.append(path);
    const label = document.createElement("span");
    label.className = "icon-label";
    label.dataset.pretext = "";
    label.append(...button.childNodes);
    button.append(svg, label);
  }

  for (const opener of document.querySelectorAll("[data-dialog]")) {
    opener.addEventListener("click", () => document.getElementById(opener.dataset.dialog).showModal());
  }
  for (const button of document.querySelectorAll("[data-close-dialog]")) {
    button.addEventListener("click", () => button.closest("dialog").close());
  }
}

export function updateRemoteAttention(element, pending, connected) {
  const label = pending ? "Pairing request" : connected ? "Controller connected" : "";
  if (element.textContent !== label) element.textContent = label;
  element.hidden = !label;
}
