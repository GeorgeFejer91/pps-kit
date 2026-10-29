// --startup-only is verified against the actual debug Runner and canonical
// compiled bytes at its configured devUrl. The default picker-dependent
// selection/inspection/preload path is prepared but remains unrun because the
// Windows automation runtime could not initialize. No selection bypass, mock
// bridge, output reservation, Arm, or Start is used by either mode.
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { applyTextSpacing, restoreTextSpacing } from "../../../../For-AI/engineering/validation/scripts/webview-layout-helpers.mjs";
const { chromium } = createRequire(import.meta.url)(process.env.PPS_PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../../../", import.meta.url));
const output = resolve(root, "artifacts/ui-workflow-check");
const packagedOnly = process.argv.includes("--packaged-only");
const layoutOnly = process.argv.includes("--layout-only");
await mkdir(output, { recursive: true });
const browser = await chromium.connectOverCDP(process.env.PPS_RUNNER_TEST_CDP || "http://127.0.0.1:19227");
try {
  let page;
  for (let attempt = 0; attempt < 20 && !page; attempt++) {
    for (const candidate of browser.contexts().flatMap(context => context.pages())) {
      if (!layoutOnly && !packagedOnly && attempt === 0 && process.argv.includes("--startup-only") && candidate.url().startsWith("http://127.0.0.1:1420/")) {
        await candidate.reload({ waitUntil: "domcontentloaded" });
      }
      if (await candidate.locator("#select-session-group").count()) { page = candidate; break; }
    }
    if (!page) await new Promise(done => setTimeout(done, 500));
  }
  assert.ok(page, "Open the actual Runner WebView first.");
  if (packagedOnly || layoutOnly) {
    assert.equal(new URL(page.url()).origin, "http://tauri.localhost",
      "Installed verification requires the packaged frontend origin");
  }
  if (layoutOnly) {
    await verifyInstalledLayout(page, browser);
  } else {
  const initial = await page.evaluate(async () => ({
    group: await window.__TAURI_INTERNALS__.invoke("native_group_status"),
    output: await window.__TAURI_INTERNALS__.invoke("native_output_status"),
    snapshot: await window.__TAURI_INTERNALS__.invoke("runner_snapshot"),
  }));
  await page.getByRole("button", { name: "Experiment Control", exact: true }).click();
  await page.locator('[data-workspace-open="package"]').click();
  if (process.argv.includes("--startup-only")) {
    assert.equal(initial.group.partCount, 0);
    assert.equal(initial.snapshot.package_verified, false);
    assert.equal(initial.snapshot.safety.local_armed, false);
    assert.equal(initial.output.reservationGeneration, null);
    await page.locator("#select-session-group").waitFor();
    assert.equal(await page.locator("#select-session-group").isEnabled(), true);
    assert.equal(await page.locator("#inspect-prepared-execution").isDisabled(), true);
    assert.equal(await page.locator("#prepare-first-audio-block").isDisabled(), true);
    const embedded = await page.evaluate(async () => {
      const script = [...document.scripts].find(script => new URL(script.src || location.href).pathname.endsWith("/assets/desktop.js"));
      if (!script) throw Error("Desktop script missing");
      const response = await fetch(script.src);
      if (!response.ok) throw Error("Embedded frontend unavailable");
      return response.text();
    });
    const digest = value => createHash("sha256").update(value).digest("hex");
    const expected = await readFile(resolve(root, "apps/runner/compiled/assets/desktop.js"));
    assert.equal(digest(embedded), digest(expected), "Actual WebView loads the current canonical Runner frontend");
    await page.screenshot({ path: resolve(output, "runner-actual-native-startup.png") });
    await writeFile(resolve(output, "runner-actual-native-startup-report.json"), JSON.stringify({ browser: browser.version(),
      scope: "actual Runner WebView/IPC startup only; native picker unavailable", frontendUrl: page.url(),
      frontendDelivery: page.url().startsWith("http://127.0.0.1:1420/") ? "canonical compiled bytes at configured debug devUrl" : "native packaged frontend",
      frontendSha256: digest(embedded),
      group: initial.group, phase: initial.snapshot.run.phase, outputPhase: initial.output.phase,
      outputReserved: false, armed: false, packageSelected: false, executed: false, physicallyQualified: false }, null, 2));
    console.log("Actual Runner native startup, canonical frontend bytes and unarmed/no-output IPC state passed.");
  } else {
  assert.equal(initial.group.partCount, 2, "Select the verified two-part fixture using the native chooser first.");
  assert.equal(initial.snapshot.package_verified, true);
  assert.equal(initial.snapshot.safety.local_armed, false);
  assert.equal(initial.output.reservationGeneration, null);
  await page.evaluate(() => {
    const bridge = window.__TAURI_INTERNALS__;
    const original = bridge.invoke.bind(bridge);
    window.runnerNativeCheck = [];
    window.restoreRunnerCheck = () => { bridge.invoke = original; };
    bridge.invoke = async (command, args, options) => {
      const result = await original(command, args, options);
      if (["inspect_prepared_execution", "prepare_first_audio_block"].includes(command)) {
        window.runnerNativeCheck.push({ command, result });
      }
      return result;
    };
  });
  await page.getByRole("button", { name: "Experiment Control", exact: true }).click();
  await page.locator("#inspect-prepared-execution").click();
  await page.locator('[data-workspace-open="overview"]').click();
  await page.locator("#execution-inspection-status").filter({ hasText: "Compiled" }).waitFor();
  await page.locator('[data-workspace-open="package"]').click();
  await page.locator("#prepare-first-audio-block").click();
  await page.waitForFunction(() => window.runnerNativeCheck.some(item => item.command === "prepare_first_audio_block"));
  const observed = await page.evaluate(async () => {
    const result = { calls: window.runnerNativeCheck,
      group: await window.__TAURI_INTERNALS__.invoke("native_group_status"),
      output: await window.__TAURI_INTERNALS__.invoke("native_output_status"),
      snapshot: await window.__TAURI_INTERNALS__.invoke("runner_snapshot"),
      status: document.getElementById("prepared-audio-status").textContent,
      recovery: document.getElementById("native-group-results-summary").textContent };
    window.restoreRunnerCheck();
    return result;
  });
  const prepared = observed.calls.find(item => item.command === "prepare_first_audio_block").result;
  assert.equal(prepared.outputQualification, "unqualified");
  assert.equal(prepared.executable, false);
  assert.ok(prepared.frames > 0);
  assert.ok(["block", "instruction"].includes(prepared.mediaKind));
  assert.equal(observed.snapshot.safety.local_armed, false);
  assert.equal(observed.output.reservationGeneration, null);
  assert.equal(observed.group.completedParts, 0, "Selection must not resume prior complete result files.");
  assert.equal(observed.group.experimentComplete, false);
  assert.match(observed.recovery, /prior group receipt/);
  await page.locator('[data-workspace-open="overview"]').click();
  await page.locator("#prepared-audio-status").scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(output, "runner-actual-native-preload.png") });
  await writeFile(resolve(output, "runner-actual-native-report.json"), JSON.stringify({ browser: browser.version(),
    scope: "actual native WebView/IPC; verified group selected through native picker; inspect/preload only",
    group: observed.group, prepared, status: observed.status, recovery: observed.recovery,
    outputReserved: false, armed: false, executed: false, physicallyQualified: false }, null, 2));
  console.log("Actual Runner native group selection, schedule inspection and audio preload passed without output reservation.");
  }
  }
} finally { await browser.close(); }

// This branch uses only existing read IPC and presentation navigation. It never
// selects a package, changes participant fields, prepares output or runs media.
async function verifyInstalledLayout(page, browser) {
  const directory = resolve(output, "runner-native-layout");
  await mkdir(directory, { recursive: true });
  const errors = [];
  page.on("pageerror", error => errors.push({ kind: "pageerror", message: error.message }));
  page.on("console", message => { if (message.type() === "error") errors.push({ kind: "console", message: message.text().slice(0, 1000) }); });
  page.on("requestfailed", request => errors.push({ kind: "requestfailed", message: request.failure()?.errorText }));
  await page.waitForFunction(() => document.getElementById("state-chip").textContent !== "Connecting");
  const cdp = await page.context().newCDPSession(page);
  const original = await page.evaluate(() => ({ zoom: document.documentElement.style.zoom,
    tab: document.querySelector("[data-tab][aria-current=page]")?.dataset.tab,
    views: [...document.querySelectorAll("[data-workspace-open][aria-current=page]")].map(node => node.dataset.workspaceOpen),
    participantForm: JSON.stringify([...document.querySelectorAll("#setup-form input,#setup-form select")].map(node => [node.id, node.value, node.checked])) }));
  const position = await page.evaluateHandle(() => ({ focus: document.activeElement,
    scroll: [...document.querySelectorAll("*")].filter(node => node.scrollHeight > node.clientHeight || node.scrollWidth > node.clientWidth).map(node => [node, node.scrollLeft, node.scrollTop]) }));
  const report = { mode: "packaged-read-only-layout", passed: false, browser: browser.version(), browserVersion: await cdp.send("Browser.getVersion"),
    origin: new URL(page.url()).origin, scope: "Actual packaged Runner WebView; idle presentation and keyboard navigation only",
    viewportMethod: "CDP CSS viewport emulation; default is the existing native viewport; OS-window resizing not assessed",
    zoomMethod: "documentElement CSS zoom 2; browser UI zoom and assistive technology not assessed",
    spacingMethod: "Reversible WCAG text-spacing CSSOM overrides; production Content Security Policy retained",
    documentPolicy: "Existing stretch workspace or explicit outer document reflow; no bounded panel clipping or inner scrolling",
    nativeCommands: ["runner_snapshot", "native_output_status"], packageSelected: false, participantEdited: false,
    outputReserved: false, armed: false, executed: false, cases: [], failures: [], errors, restored: false };
  let spacing;
  const readNativeState = () => page.evaluate(async () => {
    const snapshot = await window.__TAURI_INTERNALS__.invoke("runner_snapshot");
    const output = await window.__TAURI_INTERNALS__.invoke("native_output_status");
    return { identity: JSON.stringify([snapshot.epoch, snapshot.revision, snapshot.identity, snapshot.package_verified,
      snapshot.safety.local_armed, snapshot.run.phase, snapshot.run.complete]), armed: snapshot.safety.local_armed,
      phase: snapshot.run.phase, packageVerified: snapshot.package_verified, reservation: output.reservationGeneration };
  });
  try {
    assert.equal(report.origin, "http://tauri.localhost");
    assert.equal(await page.evaluate(() => typeof window.__TAURI_INTERNALS__?.invoke), "function");
    const before = await readNativeState();
    assert.equal(before.armed, false, "Run layout checks only on an unarmed idle target");
    assert.equal(before.reservation, null, "Do not inspect layouts while output is reserved");
    assert.equal(before.phase, "idle", "Use an idle target for presentation-only checks");
    assert.equal(before.packageVerified, false, "Do not inspect layouts on a selected package");
    const matrix = [["default"], ["desktop", 1280, 800], ["wide-short", 1920, 620],
      ["narrow", 320, 1000], ["zoom-200", 1280, 800], ["text-spacing", 1280, 800]];
    for (const [name, width, height] of matrix) {
      if (width) await cdp.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 0, mobile: false });
      await page.evaluate(zoom => { document.documentElement.style.zoom = zoom; }, name === "zoom-200" ? "2" : original.zoom);
      if (spacing) { await restoreTextSpacing(spacing); spacing = null; }
      if (name === "text-spacing") spacing = await applyTextSpacing(page);
      const record = { name, requested: width ? { width, height } : "existing viewport", views: [], keyboard: [] };
      report.cases.push(record);
      for (const [tab, views] of [["control", ["run", "participant", "package", "output", "overview"]], ["logging", [null]], ["remote", ["remote-access"]]]) {
        await page.locator(`[data-tab="${tab}"]`).click();
        assert.equal(await page.locator(`[data-tab="${tab}"]`).getAttribute("aria-current"), "page");
        for (const view of views) {
          if (view) await page.locator(`[data-workspace-open="${view}"]`).click();
          await settleLayout(page);
          const selector = view ? `#workspace-${view}` : `#runner-${tab}`;
          const geometry = await layoutGeometry(page, selector);
          record.views.push({ tab, view, ...geometry });
          if (geometry.horizontalOverflow || geometry.outside.length || geometry.clipped.length || geometry.overlaps.length || geometry.boundedOverflow.length || geometry.textNoFit.length) {
            report.failures.push({ name, selector, reason: "Rendered geometry does not fit", geometry });
          }
          await page.screenshot({ path: resolve(directory, `${name}-${view || tab}.png`) });
        }
      }
      const control = page.getByRole("button", { name: "Experiment Control", exact: true });
      await control.focus();
      await page.keyboard.press("Tab");
      assert.equal(await page.getByRole("button", { name: "Data Logging", exact: true }).evaluate(node => node === document.activeElement), true);
      record.keyboard.push(await focusedControl(page, "Data Logging navigation"));
      await page.keyboard.press("Enter");
      assert.equal(await page.locator('[data-tab="logging"]').getAttribute("aria-current"), "page");
      await control.click();
      await page.locator('[data-workspace-open="package"]').click();
      await page.getByRole("button", { name: "Choose prepared session manifest", exact: true }).focus();
      await page.keyboard.press("Tab");
      assert.equal(await page.getByRole("button", { name: "Choose participant session group", exact: true }).evaluate(node => node === document.activeElement), true);
      record.keyboard.push(await focusedControl(page, "Choose participant session group (focused, never activated)"));
      await page.locator('[data-workspace-open="participant"]').click();
      await page.getByRole("textbox", { name: "Participant code", exact: true }).focus();
      await page.keyboard.press("Tab");
      assert.equal(await page.getByRole("spinbutton", { name: "Age", exact: true }).evaluate(node => node === document.activeElement), true);
      record.keyboard.push(await focusedControl(page, "Age (focused, never edited)"));
    }
    const after = await readNativeState();
    assert.equal(after.phase, "idle");
    assert.equal(after.packageVerified, false);
    report.nativeUnarmed = after.armed === false && after.reservation === null;
    report.nativeStateUnchanged = after.identity === before.identity && report.nativeUnarmed;
    report.participantFormUnchanged = await page.evaluate(before => before === JSON.stringify([...document.querySelectorAll("#setup-form input,#setup-form select")]
      .map(node => [node.id, node.value, node.checked])), original.participantForm);
    assert.ok(report.nativeStateUnchanged && report.participantFormUnchanged, "Layout checks must retain native and participant state");
    assert.deepEqual(report.failures, []);
    assert.deepEqual(errors, [], "Installed WebView errors are retained, not suppressed");
  } catch (error) {
    report.failures.push({ reason: error.message });
    await page.screenshot({ path: resolve(directory, "failure.png") }).catch(() => {});
    throw error;
  } finally {
    try {
      if (spacing) await restoreTextSpacing(spacing);
      await page.evaluate(zoom => { document.documentElement.style.zoom = zoom; }, original.zoom);
      await cdp.send("Emulation.clearDeviceMetricsOverride");
      for (const view of original.views) {
        const tab = await page.locator(`#workspace-${view}`).evaluate(node => node.closest("[data-panel]").dataset.panel);
        await page.locator(`[data-tab="${tab}"]`).click();
        await page.locator(`[data-workspace-open="${view}"]`).click();
      }
      if (original.tab) await page.locator(`[data-tab="${original.tab}"]`).click();
      await position.evaluate(({ focus, scroll }) => { if (focus?.isConnected) focus.focus({ preventScroll: true });
        for (const [node, left, top] of scroll) if (node.isConnected) node.scrollTo({ left, top, behavior: "instant" }); });
      report.restored = true;
      report.passed = Boolean(report.nativeStateUnchanged && report.participantFormUnchanged && report.cases.length === 6 && !report.failures.length && !errors.length);
    } catch (error) {
      report.failures.push({ reason: `Restoration failed: ${error.message}` });
      throw error;
    } finally {
      await writeFile(resolve(directory, "report.json"), JSON.stringify(report, null, 2));
      await cdp.detach();
    }
  }
  assert.ok(report.passed, "The complete installed layout report must pass");
  console.log(`Packaged Runner layout-only checks passed: ${directory}`);
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
      horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
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
  // Keyboard focus starts a 120ms CSS transition on form fields. Observe its
  // finished paint, not a transparent zero-size shadow at the first frame.
  const paintHandle = await page.waitForFunction(() => {
    const node = document.activeElement, style = getComputedStyle(node);
    const visibleColor = color => color !== "transparent" && !/^rgba\([^)]*,\s*0(?:\.0*)?\)$/.test(color);
    const outline = style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0 && visibleColor(style.outlineColor);
    const shadow = style.boxShadow.split(/,(?![^(]*\))/).some(value => {
      const color = value.match(/rgba?\([^)]+\)/)?.[0];
      const lengths = value.replace(/rgba?\([^)]+\)/g, "").match(/-?[\d.]+px/g) || [];
      return color && visibleColor(color) && lengths.some(length => parseFloat(length) !== 0);
    });
    const settled = node.getAnimations().every(animation => animation.playState === "finished");
    return node.matches(":focus-visible") && settled && (outline || shadow) ? { outline, shadow, settled } : false;
  }, undefined, { timeout: 5000 });
  const focusPaint = await paintHandle.jsonValue();
  await paintHandle.dispose();
  const result = await page.evaluate(() => { const node = document.activeElement, b = node.getBoundingClientRect(), style = getComputedStyle(node);
    const hit = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2);
    return { id: node.id, box: b.toJSON(), focusVisible: node.matches(":focus-visible"), outline: style.outline, outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth,
      boxShadow: style.boxShadow, reachable: b.left >= -1 && b.top >= -1 && b.right <= innerWidth + 1 && b.bottom <= innerHeight + 1 && (hit === node || node.contains(hit)) }; });
  assert.ok(result.reachable, `${name} is not covered or outside the viewport`);
  assert.ok(result.focusVisible, `${name} has keyboard focus`);
  assert.ok(focusPaint.outline || focusPaint.shadow, `${name} retains a painted focus indicator`);
  return { name, accessibleNode: (await page.locator(":focus").ariaSnapshot()).split("\n")[0], ...result, focusPaint };
}
