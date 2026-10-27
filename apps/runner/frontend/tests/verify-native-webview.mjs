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
const { chromium } = createRequire(import.meta.url)(process.env.PPS_PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../../../", import.meta.url));
const output = resolve(root, "artifacts/ui-workflow-check");
await mkdir(output, { recursive: true });
const browser = await chromium.connectOverCDP(process.env.PPS_RUNNER_TEST_CDP || "http://127.0.0.1:19227");
try {
  let page;
  for (let attempt = 0; attempt < 20 && !page; attempt++) {
    for (const candidate of browser.contexts().flatMap(context => context.pages())) {
      if (attempt === 0 && process.argv.includes("--startup-only") && candidate.url().startsWith("http://127.0.0.1:1420/")) {
        await candidate.reload({ waitUntil: "domcontentloaded" });
      }
      if (await candidate.locator("#select-session-group").count()) { page = candidate; break; }
    }
    if (!page) await new Promise(done => setTimeout(done, 500));
  }
  assert.ok(page, "Open the actual Runner WebView first.");
  const initial = await page.evaluate(async () => ({
    group: await window.__TAURI_INTERNALS__.invoke("native_group_status"),
    output: await window.__TAURI_INTERNALS__.invoke("native_output_status"),
    snapshot: await window.__TAURI_INTERNALS__.invoke("runner_snapshot"),
  }));
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
  await page.locator("#execution-inspection-status").filter({ hasText: "Compiled" }).waitFor();
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
  await page.locator("#prepared-audio-status").scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(output, "runner-actual-native-preload.png") });
  await writeFile(resolve(output, "runner-actual-native-report.json"), JSON.stringify({ browser: browser.version(),
    scope: "actual native WebView/IPC; verified group selected through native picker; inspect/preload only",
    group: observed.group, prepared, status: observed.status, recovery: observed.recovery,
    outputReserved: false, armed: false, executed: false, physicallyQualified: false }, null, 2));
  console.log("Actual Runner native group selection, schedule inspection and audio preload passed without output reservation.");
  }
} finally { await browser.close(); }
