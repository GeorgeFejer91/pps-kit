import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { installNativeExternalLinkTrace } from "./native-external-trace.mjs";
import { applyTextSpacing, restoreTextSpacing } from "../../../../For-AI/engineering/validation/scripts/webview-layout-helpers.mjs";
const layoutOnly = process.argv.includes("--layout-only");
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PPS_PLAYWRIGHT_MODULE || "playwright");
let browser;
for (let attempt = 0; attempt < 40; attempt++) {
  try {
    browser = await chromium.connectOverCDP(process.env.PPS_DESIGNER_TEST_CDP || "http://127.0.0.1:19225");
    break;
  } catch (error) {
    if (attempt === 39 || !String(error).includes("ECONNREFUSED")) throw error;
    await new Promise(resolve => setTimeout(resolve, 250));
  }
}
try {
  const context = browser.contexts()[0];
  const page = context.pages()[0] || await context.waitForEvent("page", { timeout: 10_000 });
  await page.waitForURL(/^http:\/\/tauri\.localhost\//);
  const requests = [];
  const failures = [];
  const recordFailure = entry => { if (failures.length < 30) failures.push({ ...entry, message: String(entry.message || "").slice(0, 1000) }); };
  page.on("request", request => requests.push(request.url()));
  page.on("pageerror", error => recordFailure({ kind: "pageerror", message: error.message }));
  page.on("console", message => { if (message.type() === "error") recordFailure({ kind: "console", message: message.text() }); });
  page.on("requestfailed", request => recordFailure({ kind: "requestfailed", url: request.url(), message: request.failure()?.errorText }));
  const acceptDialog = dialog => dialog.accept();
  if (!layoutOnly) page.on("dialog", acceptDialog);
  await page.waitForFunction(() => window.PPSDesignerApp?.getState()?.design);
  assert.equal(await page.evaluate(() => window.PPSDesignerApp.isNative()), true);
  if (layoutOnly) {
    await verifyInstalledLayout(page, browser, failures);
  } else {
  assert.equal(await page.locator("#native-import-profile").isVisible(), true);
  assert.equal(await page.locator("#native-import-profile").isEnabled(), true);
  assert.equal(await page.evaluate(() => Boolean(window.PPSDesignerApp.getState().custom_workflow?.is_custom)), false,
    "Run this control journey in a fresh isolated app profile; do not overwrite an existing draft");
  await page.locator("#edit-mode-button").click();
  await page.locator("#customize-study-name").fill("Native WebView acceptance fixture");
  await page.locator("#customize-submit").click();
  await page.locator("#customize-modal").waitFor({ state: "hidden" });
  await page.waitForFunction(() => window.PPSDesignerApp.getState().custom_workflow?.edit_step === "stimulus");
  await page.locator("#trajectory-frame").scrollIntoViewIfNeeded();
  try {
    await page.waitForFunction(() => {
      const frame = document.getElementById("trajectory-frame");
      return frame.src !== "about:blank" && typeof frame.contentWindow?.updateTrajectory === "function";
    }, null, { timeout: 30_000 });
  } catch (error) {
    const frame = await page.locator("#trajectory-frame").evaluate(node => ({ src: node.src,
      lazySrc: node.dataset.lazySrc, bounds: node.getBoundingClientRect().toJSON() }));
    throw new Error(`Trajectory viewer did not load after real Stimulus navigation: ${JSON.stringify({ frame, failures })}`, { cause: error });
  }
  await page.locator('.noise-type-button[data-noise-type="white"]').click();
  await page.locator("#bake-label").fill("Native WebView white");
  await page.locator("#movement-duration").fill("1");
  await page.locator("#start-hold").fill("0.2");
  await page.locator("#end-hold").fill("0.2");
  await page.locator("#bake-stimulus").click();
  await page.waitForFunction(() => document.getElementById("native-cancel-generation").disabled);
  assert.match(await page.locator("#toast").innerText(), /algorithm|opt.in/i);
  assert.equal(await page.evaluate(() => window.PPSDesignerApp.getState().design.noises.some(source => source.label === "Native WebView white")), false);
  await page.locator("#native-source-opt-in").check();
  await page.locator("#native-source-seed").fill("123");
  await page.locator("#bake-stimulus").click();
  await page.waitForFunction(() => document.getElementById("native-cancel-generation").disabled, null, { timeout: 90_000 });
  const snapshot = await page.evaluate(() => window.PPSDesignerApp.getState());
  const source = snapshot.design.noises.find(source => source.label === "Native WebView white");
  assert.ok(source, await page.locator("#toast").innerText());
  assert.match(source.prebaked_path, /^native-assets\/[a-f0-9]{64}\.wav$/);
  const asset = snapshot.preload_inventory.assets.find(asset => asset.path === source.prebaked_path);
  assert.equal(asset.channels, 2);
  assert.equal(asset.provenance.numpy_seed_compatible, false);
  assert.deepEqual(snapshot.block_csv_preview, {});
  assert.equal(snapshot.project_segments["5_block_csv_preview"].status, "stale");
  await page.evaluate(() => {
    window.nativePreviewStarts = 0;
    const create = AudioContext.prototype.createBufferSource;
    AudioContext.prototype.createBufferSource = function (...args) {
      const source = create.apply(this, args); const start = source.start;
      source.start = function (...parameters) { window.nativePreviewStarts++; return start.apply(this, parameters); };
      return source;
    };
  });
  const play = page.locator('[data-preview-source-label="Native WebView white"]').first();
  await play.click();
  await page.waitForFunction(() => window.nativePreviewStarts > 0);
  await play.click();
  assert.ok(!requests.some(url => /https?:.*\/api\//.test(url)), "native errors and success never call the HTTP backend");
  const externalWebLinkHandoff = await verifyExternalWebLink(page);
  await page.locator("#native-generation-controls").scrollIntoViewIfNeeded();
  await page.screenshot({ path: "artifacts/ui-workflow-check/native-generation.png" });
  page.off("dialog", acceptDialog);
  const mapperTemplateNavigation = await verifyMapperTemplateNavigation(page);
  await writeFile("artifacts/ui-workflow-check/native-webview-report.json", JSON.stringify({
    native: true, sharedHtml: true, trajectoryIframe: true, customDraftThroughControls: true, algorithmOptInRequired: true,
    actualRenderer: asset.provenance.renderer.schema, channels: asset.channels, sha256: asset.sha256,
    downstreamInvalidated: true, generatedPreviewStartedMuted: true, httpFallbackRequests: 0,
    externalWebLinkHandoff,
    mapperTemplateNavigation,
  }, null, 2));
  console.log("Native WebView: real controls, required algorithm opt-in, actual C++ audio publication, downstream invalidation, no HTTP fallback passed.");
  }
} finally { await browser.close(); }

async function verifyMapperTemplateNavigation(page) {
  await page.locator("#movement-duration").fill("1.25");
  assert.equal(await page.evaluate(() => PPSDesignerApp.isDirty()), true);
  const draft = await page.evaluate(() => JSON.stringify(PPSDesignerApp.getState()));
  await page.getByRole("tab", { name: "Documentation", exact: true }).click();
  await page.locator("[data-publication-network-root]").scrollIntoViewIfNeeded();
  await page.waitForFunction(() => document.querySelector("[data-publication-network-root]").dataset.publicationNetworkState === "ready");
  await page.locator("#publication-network-search").fill("10.1016/j.cub.2013.01.043");
  await page.locator(".publication-network-result-button").click();
  const study = page.locator("#publication-network-detail [data-study-id]:has([data-open-designer-template])").first();
  if (!await study.evaluate(node => node.open)) await study.locator(":scope > summary").click();
  const link = study.locator("[data-open-designer-template]").first();
  const templateId = await link.getAttribute("data-open-designer-template");
  const pages = page.context().pages().length;
  const cancel = page.waitForEvent("dialog").then(async dialog => {
    assert.match(dialog.message(), /Discard.*load another profile/);
    await dialog.dismiss();
  });
  await link.click();
  await cancel;
  assert.equal(await page.evaluate(() => JSON.stringify(PPSDesignerApp.getState())), draft, "Cancel retains the complete custom draft");
  assert.equal(await page.locator("body").getAttribute("data-active-page"), "documentation", "Cancel retains the mapper");
  const confirm = page.waitForEvent("dialog").then(dialog => dialog.accept());
  await link.click();
  await confirm;
  await page.waitForFunction(id => PPSDesignerApp.getState().design.study_profile_id === id
    && !PPSDesignerApp.getState().custom_workflow?.is_custom && document.body.dataset.activePage === "toolkit", templateId);
  assert.equal(new URL(page.url()).searchParams.get("page"), "toolkit", "Preset navigation updates the mapper's page query");
  assert.equal(await page.evaluate(() => document.activeElement.id), "study-segment");
  assert.equal(page.context().pages().length, pages, "Native preset links stay in the existing app WebView");
  return { templateId, unsavedDraftCancelPreserved: true, confirmedPresetLoaded: true, existingWebview: true, focusMovedToStudy: true };
}

async function verifyExternalWebLink(page) {
  await page.evaluate(installNativeExternalLinkTrace);
  try {
    await page.getByRole("tab", { name: "Downloads", exact: true }).click();
    const originalUrl = page.url();
    const link = page.locator("#download-software");
    const url = await link.getAttribute("href");
    await link.click();
    try {
      await page.waitForFunction(() => window.externalLinkReceipts.some(receipt => !receipt.pending));
    } catch (error) {
      const trace = await page.evaluate(() => ({ receipts: window.externalLinkReceipts,
        invokeWritable: Object.getOwnPropertyDescriptor(window.__TAURI_INTERNALS__, "invoke").writable }));
      throw new Error(`Native external-link fetch acknowledgement was not observed: ${JSON.stringify(trace)}`, { cause: error });
    }
    const receipts = await page.evaluate(() => window.externalLinkReceipts);
    assert.deepEqual(receipts, [{ url, method: "POST", pending: false, reply: "ok", opened: true }], "One real link click receives the genuine OS browser acknowledgement exactly once");
    assert.equal(page.url(), originalUrl, "External links do not navigate the privileged app WebView");
    return { acceptedByOs: true, mainWebviewStayedLocal: true,
      scope: "System browser accepted the public release URL; remote availability is checked at publication" };
  } finally {
    await page.evaluate(() => window.restoreExternalLinkTrace());
    await page.getByRole("tab", { name: "Experiment Designer", exact: true }).click();
  }
}

// Presentation-only installed check. Never creates a draft or activates a
// generation/review/import control. CSS viewport emulation is not OS resizing.
async function verifyInstalledLayout(page, browser, errors) {
  const output = resolve(fileURLToPath(new URL("../../../../", import.meta.url)), "artifacts/ui-workflow-check/designer-native-layout");
  await mkdir(output, { recursive: true });
  await page.evaluate(async () => { await window.PPSDesignerApp.ready; });
  const cdp = await page.context().newCDPSession(page);
  const original = await page.evaluate(() => ({ zoom: document.documentElement.style.zoom,
    design: JSON.stringify({ design: PPSDesignerApp.getState().design, workflow: PPSDesignerApp.getState().custom_workflow }) }));
  const position = await page.evaluateHandle(() => ({ focus: document.activeElement,
    scroll: [...document.querySelectorAll("*")].filter(node => node.scrollHeight > node.clientHeight || node.scrollWidth > node.clientWidth).map(node => [node, node.scrollLeft, node.scrollTop]) }));
  const report = { mode: "packaged-read-only-layout", passed: false, browser: browser.version(), browserVersion: await cdp.send("Browser.getVersion"),
    origin: new URL(page.url()).origin, scope: "Actual packaged Designer WebView; presentation and keyboard navigation only",
    viewportMethod: "CDP CSS viewport emulation; default is the existing native viewport; OS-window resizing not assessed",
    zoomMethod: "documentElement CSS zoom 2; browser UI zoom and assistive technology not assessed",
    spacingMethod: "Reversible WCAG text-spacing CSSOM overrides; production Content Security Policy retained",
    documentPolicy: "Workflow uses outer document flow; About text has its existing separate reading region",
    draftCreated: false, profileSelected: false, generationStarted: false, nativeReviewBuilt: false,
    cases: [], failures: [], errors, restored: false };
  let spacing, openedAbout = false;
  try {
    assert.equal(report.origin, "http://tauri.localhost");
    assert.equal(await page.evaluate(() => typeof window.__TAURI_INTERNALS__?.invoke), "function");
    assert.equal(await page.locator('[role="dialog"]:visible').count(), 0, "Close existing dialogs before a read-only layout check");
    const matrix = [["default"], ["desktop", 1280, 800], ["wide-short", 1920, 620],
      ["narrow", 320, 1000], ["text-spacing", 1280, 800], ["zoom-200", 1280, 800]];
    for (const [name, width, height] of matrix) {
      if (width) await cdp.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 0, mobile: false });
      await page.evaluate(zoom => { document.documentElement.style.zoom = zoom; }, name === "zoom-200" ? "2" : original.zoom);
      if (spacing) { await restoreTextSpacing(spacing); spacing = null; }
      if (name === "text-spacing") spacing = await applyTextSpacing(page);
      const record = { name, requested: width ? { width, height } : "existing viewport", views: [], keyboard: [] };
      report.cases.push(record);
      for (const selector of ["#study-segment", "#native-generation-controls", "#native-execution"]) {
        await page.locator(selector).scrollIntoViewIfNeeded();
        await settleLayout(page);
        const geometry = await layoutGeometry(page, selector);
        record.views.push({ selector, ...geometry });
        if (geometry.horizontalOverflow || geometry.outside.length || geometry.clipped.length || geometry.overlaps.length || geometry.boundedOverflow.length || geometry.textNoFit.length) {
          report.failures.push({ name, selector, reason: "Rendered geometry does not fit", geometry });
        }
        await page.screenshot({ path: resolve(output, `${name}-${selector.slice(1)}.png`) });
      }
      assert.equal(await page.getByRole("button", { name: "Open portable profile", exact: true }).getAttribute("id"), "native-import-profile");
      assert.equal(await page.getByRole("spinbutton", { name: "Native source seed", exact: true }).getAttribute("id"), "native-source-seed");
      assert.equal(await page.getByRole("button", { name: "Build full native review", exact: true }).getAttribute("id"), "native-build-review");
      await page.locator("#native-import-profile").focus();
      await page.keyboard.press("Tab");
      const trigger = page.getByRole("button", { name: "About Segment 0: Choose or Create Study", exact: true });
      assert.equal(await trigger.evaluate(node => node === document.activeElement), true, "Tab follows the native import control in DOM order");
      record.keyboard.push(await focusedControl(page, "About Segment 0"));
      await page.keyboard.press("Enter");
      openedAbout = true;
      const close = page.locator("#segment-info-modal-close");
      await close.waitFor();
      await close.focus();
      await page.keyboard.press("Tab");
      const body = page.getByRole("region", { name: "Segment information", exact: true });
      assert.equal(await body.evaluate(node => node === document.activeElement), true);
      record.keyboard.push(await focusedControl(page, "About reading region"));
      const dialog = await page.locator("#segment-info-modal [role=dialog]").count()
        ? page.locator("#segment-info-modal [role=dialog]") : page.locator("#segment-info-modal");
      const box = await dialog.boundingBox();
      const viewport = await page.evaluate(() => ({ width: innerWidth, height: innerHeight }));
      record.about = { box, viewport, readingRegion: await body.evaluate(node => ({ box: node.getBoundingClientRect().toJSON(),
        height: node.clientHeight, scrollHeight: node.scrollHeight })) };
      assert.ok(box && box.x >= -1 && box.y >= -1 && box.x + box.width <= viewport.width + 1 && box.y + box.height <= viewport.height + 1, "About anchors fit the viewport");
      await page.screenshot({ path: resolve(output, `${name}-about.png`) });
      await page.keyboard.press("Escape");
      openedAbout = false;
      assert.equal(await trigger.evaluate(node => node === document.activeElement), true, "Closing About restores focus to its actual trigger");
      record.focusReturned = true;
    }
    const unchanged = await page.evaluate(before => before === JSON.stringify({ design: PPSDesignerApp.getState().design,
      workflow: PPSDesignerApp.getState().custom_workflow }), original.design);
    report.designAndWorkflowUnchanged = unchanged;
    assert.ok(unchanged, "Layout checks must not change the design or custom workflow");
    assert.deepEqual(report.failures, []);
    assert.deepEqual(errors, [], "Installed WebView errors are retained, not suppressed");
  } catch (error) {
    report.failures.push({ reason: error.message });
    await page.screenshot({ path: resolve(output, "failure.png") }).catch(() => {});
    throw error;
  } finally {
    try {
      if (openedAbout && await page.locator("#segment-info-modal:visible").count()) await page.keyboard.press("Escape");
      if (spacing) await restoreTextSpacing(spacing);
      await page.evaluate(zoom => { document.documentElement.style.zoom = zoom; }, original.zoom);
      await cdp.send("Emulation.clearDeviceMetricsOverride");
      await position.evaluate(({ focus, scroll }) => { if (focus?.isConnected) focus.focus({ preventScroll: true });
        for (const [node, left, top] of scroll) if (node.isConnected) node.scrollTo({ left, top, behavior: "instant" }); });
      report.restored = true;
      report.passed = Boolean(report.designAndWorkflowUnchanged && report.cases.length === 6 && !report.failures.length && !errors.length);
    } catch (error) {
      report.failures.push({ reason: `Restoration failed: ${error.message}` });
      throw error;
    } finally {
      await writeFile(resolve(output, "report.json"), JSON.stringify(report, null, 2));
      await cdp.detach();
    }
  }
  assert.ok(report.passed, "The complete installed layout report must pass");
  console.log(`Packaged Designer layout-only checks passed: ${output}`);
}

async function settleLayout(page) {
  await page.evaluate(async () => { await document.fonts.ready;
    for (let i = 0; i < 4; i++) await new Promise(done => requestAnimationFrame(done)); });
}

async function layoutGeometry(page, selector) {
  return page.evaluate(selector => {
    const scope = document.querySelector(selector);
    const visible = node => {
      if (!node.getClientRects().length || getComputedStyle(node).visibility === "hidden") return false;
      // This form-state select is deliberately transparent and removed from the
      // accessibility/tab order; its painted combobox is measured instead.
      if (node.matches("select.bounded-select-native[aria-hidden=true]") && node.tabIndex === -1
        && Number(getComputedStyle(node).opacity) === 0 && getComputedStyle(node).pointerEvents === "none") return false;
      for (let p = node.parentElement; p; p = p.parentElement) {
        if (p.matches("details:not([open])") && !p.querySelector(":scope > summary")?.contains(node)) return false;
      }
      return true;
    };
    const box = node => ({ id: node.id || node.className, ...node.getBoundingClientRect().toJSON() });
    const controls = [...scope.querySelectorAll("button,input,select,textarea,summary")].filter(visible);
    const labels = [...scope.querySelectorAll("button,label,[data-pretext-result]")].filter(visible);
    const overlaps = [];
    for (let i = 0; i < controls.length; i++) for (let j = i + 1; j < controls.length; j++) {
      if (controls[i].contains(controls[j]) || controls[j].contains(controls[i])) continue;
      const a = controls[i].getBoundingClientRect(), b = controls[j].getBoundingClientRect();
      if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1) overlaps.push([box(controls[i]), box(controls[j])]);
    }
    return { viewport: { width: innerWidth, height: innerHeight, visualWidth: visualViewport?.width, visualHeight: visualViewport?.height, dpr: devicePixelRatio },
      userAgent: navigator.userAgent, container: box(scope), documentHeight: document.documentElement.scrollHeight,
      documentWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth,
      horizontalOffenders: document.documentElement.scrollWidth > innerWidth + 1
        ? [...document.querySelectorAll("body *")].filter(visible).filter(node => { const b = node.getBoundingClientRect();
          return b.left < -1 || b.right > innerWidth + 1; }).slice(0, 30).map(box) : [],
      // Transparent form controls can still enlarge the scrollable document.
      // Keep these separate from painted-control overlap checks, never mask
      // the whole-page overflow just because its cause is not painted.
      layoutHorizontalOffenders: document.documentElement.scrollWidth > innerWidth + 1
        ? [...document.querySelectorAll("body *")].filter(node => node.getClientRects().length).filter(node => {
          const b = node.getBoundingClientRect(); return b.left < -1 || b.right > innerWidth + 1;
        }).slice(0, 40).map(node => { const style = getComputedStyle(node); return { ...box(node), tag: node.tagName,
          opacity: style.opacity, visibility: style.visibility, pointerEvents: style.pointerEvents,
          ariaHidden: node.getAttribute("aria-hidden"), overflowX: style.overflowX, position: style.position }; }) : [],
      horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
      controls: controls.map(box), overlaps, outside: controls.filter(node => { const r = node.getBoundingClientRect(); return r.left < -1 || r.right > innerWidth + 1; }).map(box),
      clipped: labels.filter(node => { const r = document.createRange(); r.selectNodeContents(node); const text = r.getBoundingClientRect(), b = node.getBoundingClientRect();
        return text.width && (text.left < b.left - 2 || text.right > b.right + 2 || text.top < b.top - 2 || text.bottom > b.bottom + 2); }).map(box),
      boundedOverflow: [scope, ...scope.querySelectorAll(".panel")].filter(visible).filter(node =>
        (node.scrollWidth > node.clientWidth + 2 && getComputedStyle(node).overflowX !== "visible") ||
        (node.scrollHeight > node.clientHeight + 2 && getComputedStyle(node).overflowY !== "visible")).map(box),
      textNoFit: labels.filter(node => node.dataset.pretextDomResult === "no-fit").map(box) };
  }, selector);
}

async function focusedControl(page, name) {
  // Keyboard focus may trigger the document's existing smooth scroll. Wait for
  // its real viewport/hit-test condition; do not scroll or refocus for the test.
  await page.waitForFunction(() => {
    const node = document.activeElement, b = node.getBoundingClientRect();
    const hit = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2);
    return b.left >= -1 && b.top >= -1 && b.right <= innerWidth + 1 && b.bottom <= innerHeight + 1
      && (hit === node || node.contains(hit));
  }, null, { timeout: 3000 });
  const result = await page.evaluate(() => { const node = document.activeElement, b = node.getBoundingClientRect(), style = getComputedStyle(node);
    const hit = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2);
    return { id: node.id, box: b.toJSON(), focusVisible: node.matches(":focus-visible"), outline: style.outline, outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth,
      boxShadow: style.boxShadow, reachable: b.left >= -1 && b.top >= -1 && b.right <= innerWidth + 1 && b.bottom <= innerHeight + 1 && (hit === node || node.contains(hit)) }; });
  assert.ok(result.reachable, `${name} is not covered or outside the viewport`);
  assert.ok(result.focusVisible, `${name} has keyboard focus`);
  assert.ok((result.outlineStyle !== "none" && parseFloat(result.outlineWidth) > 0) || result.boxShadow !== "none", `${name} retains a focus indicator`);
  return { name, accessibleNode: (await page.locator(":focus").ariaSnapshot()).split("\n")[0], ...result };
}
