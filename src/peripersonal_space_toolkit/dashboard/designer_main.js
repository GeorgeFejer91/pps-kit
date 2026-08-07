const DATABASE_NAME = "pps-designer";
const DATABASE_VERSION = 1;
const DRAFT_STORE = "drafts";
const ASSET_STORE = "assets";

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(DRAFT_STORE)) database.createObjectStore(DRAFT_STORE);
      if (!database.objectStoreNames.contains(ASSET_STORE)) database.createObjectStore(ASSET_STORE);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function put(storeName, key, value) {
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(storeName, "readwrite");
    transaction.objectStore(storeName).put(value, key);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  }).finally(() => database.close());
}

async function get(storeName, key) {
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    const request = database.transaction(storeName).objectStore(storeName).get(key);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  }).finally(() => database.close());
}

const drafts = {
  async save(snapshot) {
    try {
      await put(DRAFT_STORE, "active", { savedAt: new Date().toISOString(), snapshot });
      document.dispatchEvent(new CustomEvent("pps-designer-saved"));
    } catch (error) {
      throw new Error(`Browser storage failed (${error?.message || error}). Download the profile bundle now to avoid losing changes.`);
    }
  },
  async load() {
    return (await get(DRAFT_STORE, "active"))?.snapshot || null;
  },
  async storeAudio(file) {
    const bytes = await file.arrayBuffer();
    const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
      .map((value) => value.toString(16).padStart(2, "0")).join("");
    const id = `${digest}.${String(file.name).split(".").pop()?.toLowerCase() || "wav"}`;
    const record = { id, name: file.name, type: file.type || "audio/wav", bytes, size: file.size };
    await put(ASSET_STORE, id, record);
    return { ...record, url: URL.createObjectURL(new Blob([bytes], { type: record.type })) };
  },
  asset: (id) => get(ASSET_STORE, id),
};

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function littleEndian(values) {
  const bytes = [];
  for (const [value, width] of values) {
    for (let index = 0; index < width; index += 1) bytes.push((value >>> (8 * index)) & 0xff);
  }
  return bytes;
}

function zipStored(files) {
  const encoder = new TextEncoder();
  const local = [];
  const central = [];
  let offset = 0;
  for (const file of files) {
    const name = encoder.encode(file.name);
    const data = file.bytes instanceof Uint8Array ? file.bytes : new Uint8Array(file.bytes);
    const checksum = crc32(data);
    const localHeader = new Uint8Array([
      ...littleEndian([[0x04034b50, 4], [20, 2], [0x0800, 2], [0, 2], [0, 2], [0, 2], [checksum, 4], [data.length, 4], [data.length, 4], [name.length, 2], [0, 2]]),
      ...name,
    ]);
    local.push(localHeader, data);
    central.push(new Uint8Array([
      ...littleEndian([[0x02014b50, 4], [20, 2], [20, 2], [0x0800, 2], [0, 2], [0, 2], [0, 2], [checksum, 4], [data.length, 4], [data.length, 4], [name.length, 2], [0, 2], [0, 2], [0, 2], [0, 2], [0, 4], [offset, 4]]),
      ...name,
    ]));
    offset += localHeader.length + data.length;
  }
  const centralSize = central.reduce((sum, value) => sum + value.length, 0);
  const end = new Uint8Array(littleEndian([[0x06054b50, 4], [0, 2], [0, 2], [files.length, 2], [files.length, 2], [centralSize, 4], [offset, 4], [0, 2]]));
  return new Blob([...local, ...central, end], { type: "application/vnd.pps-profile+zip" });
}

async function sha256(bytes) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))]
    .map((value) => value.toString(16).padStart(2, "0")).join("");
}

async function exportBundle(snapshot) {
  const encoder = new TextEncoder();
  const design = structuredClone(snapshot.design);
  const assetIds = new Set();
  for (const item of [...(design.custom_looming_files || []), ...(design.prestimulus_files || [])]) {
    if (item.browser_asset_id) assetIds.add(item.browser_asset_id);
  }
  const assetRecords = [];
  const files = [];
  for (const id of assetIds) {
    const asset = await drafts.asset(id);
    if (!asset) throw new Error(`Local browser audio is missing: ${id}`);
    const path = `assets/${id}`;
    const bytes = new Uint8Array(asset.bytes);
    files.push({ name: path, bytes });
    assetRecords.push({ logical_id: id, path, sha256: await sha256(bytes), bytes: bytes.length, media_type: asset.type, source_name: asset.name });
  }
  const profileId = `custom_${String(design.name || "profile").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 32) || "profile"}`;
  const profile = { schema: "pps-study-profile.v1", profile_id: profileId, profile_kind: "custom", display_name: design.name, design, assets: assetRecords };
  const profileBytes = encoder.encode(`${JSON.stringify(profile, null, 2)}\n`);
  files.unshift({ name: "profile.json", bytes: profileBytes });
  const inventory = [];
  for (const file of files) inventory.push({ path: file.name, sha256: await sha256(file.bytes), bytes: file.bytes.length });
  const manifest = {
    schema: "pps-profile-bundle.v1",
    profile_id: profileId,
    profile_kind: "custom",
    display_name: design.name,
    created_at: new Date().toISOString(),
    capability_provenance: "hosted_compose",
    parent: { profile_id: design.study_profile_reference_parameters?.customized_from_profile_id || "" },
    files: inventory,
  };
  files.unshift({ name: "manifest.json", bytes: encoder.encode(`${JSON.stringify(manifest, null, 2)}\n`) });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(zipStored(files));
  link.download = `${profileId}.pps-profile`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 2000);
}

async function exportDesktopBundle(snapshot) {
  const response = await fetch("/api/profiles/export-bundle", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ design: snapshot.design, display_name: snapshot.design?.name }),
  });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Profile export failed.");
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] || "custom_profile.pps-profile";
  if (window.pywebview?.api?.save_profile_bundle) {
    const reader = new FileReader();
    const content = await new Promise((resolve, reject) => {
      reader.onload = () => resolve(String(reader.result).split(",")[1]);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
    await window.pywebview.api.save_profile_bundle(content, filename);
    return;
  }
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 2000);
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("ppsDesigner.theme", theme);
  const toggle = document.getElementById("designer-theme-toggle");
  if (toggle) {
    toggle.setAttribute("aria-pressed", String(theme === "dark"));
    const nextThemeLabel = theme === "dark" ? "Use light theme" : "Use dark theme";
    toggle.setAttribute("aria-label", nextThemeLabel);
    toggle.title = nextThemeLabel;
  }
}

function initializeChrome() {
  const desktop = new URLSearchParams(location.search).get("desktop") === "1";
  document.body.classList.toggle("desktop-applet", desktop);
  document.getElementById("designer-capability-badge").textContent = desktop ? "desktop full" : "hosted compose";
  applyTheme(localStorage.getItem("ppsDesigner.theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  document.getElementById("designer-theme-toggle")?.addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
  document.getElementById("designer-help")?.addEventListener("click", () => document.querySelector('[data-segment-info="study"]')?.click());
  const saveState = document.getElementById("designer-save-state");
  document.addEventListener("input", (event) => {
    if (!event.target.closest?.("#toolkit-page")) return;
    saveState.textContent = "unsaved";
    saveState.className = "status-label required";
  });
  document.addEventListener("pps-designer-saved", () => {
    saveState.textContent = "saved";
    saveState.className = "status-label ready";
  });
  document.getElementById("export-profile-bundle")?.addEventListener("click", async () => {
    try {
      const snapshot = window.PPSDesignerApp.getState();
      if (desktop) await exportDesktopBundle(snapshot); else await exportBundle(snapshot);
    } catch (error) { alert(error.message || String(error)); }
  });
  for (const segment of document.querySelectorAll(".decision-segment")) {
    const heading = segment.querySelector(":scope > .segment-heading");
    if (!heading || heading.querySelector(".segment-collapse-button")) continue;
    const title = heading.querySelector("h2")?.textContent?.trim() || "workflow segment";
    const kicker = heading.querySelector(".segment-kicker")?.textContent?.trim() || "Segment";
    if (!segment.id) {
      const stableId = heading.querySelector("h2")?.id
        || title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      segment.id = `segment-${stableId}`;
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "segment-collapse-button";
    button.textContent = "Collapse";
    button.setAttribute("aria-controls", segment.id);
    button.setAttribute("aria-expanded", "true");
    button.setAttribute("aria-label", `Collapse ${kicker}: ${title}`);
    button.addEventListener("click", () => {
      segment.classList.toggle("collapsed");
      const collapsed = segment.classList.contains("collapsed");
      button.textContent = collapsed ? "Expand" : "Collapse";
      button.setAttribute("aria-expanded", String(!collapsed));
      button.setAttribute("aria-label", `${collapsed ? "Expand" : "Collapse"} ${kicker}: ${title}`);
    });
    heading.appendChild(button);
  }
  if (!desktop) {
    const restore = async () => {
      const stored = await drafts.load().catch(() => null);
      if (stored?.custom_workflow?.is_custom) window.PPSDesignerApp?.restoreHostedDraft(stored);
    };
    window.setTimeout(restore, 900);
  }
}

window.PPSDesigner = Object.freeze({ drafts, exportBundle });
initializeChrome();
