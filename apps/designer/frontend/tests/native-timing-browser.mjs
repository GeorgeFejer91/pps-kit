import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";

// Real HTML controls with an explicit native IPC fixture, not native timing qualification.
export async function verifyNativeTimingReview(browser, base, output) {
  const hosted = await browser.newPage();
  await hosted.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1&template=noel_2015_walking_full_body_action`);
  await hosted.waitForFunction(() => window.PPSDesignerApp?.getState()?.design?.study_profile_id === "noel_2015_walking_full_body_action");
  const snapshot = await hosted.evaluate(() => window.PPSDesignerApp.getState());
  await hosted.close();
  const receipt = { native_iti_materialization_policy: "toolkit_uniform_integer_ms_std_rng_0_8_8.v1", native_iti_anchor: "after_trial_audio_end",
    native_iti_seed_sha256: "a".repeat(64), native_iti_range_min_ms: 1000, native_iti_range_max_ms: 1500, native_resolved_iti_ms: 1234,
    native_iti_frames: 54419, native_session_duration_ms: snapshot.block_csv_preview.blocks[0].preview_rows[0].duration_ms + 1234, native_iti_source_distribution_reported: false,
    native_iti_source_anchor_reported: false, native_iti_legacy_compatible: false };
  Object.assign(snapshot.block_csv_preview.blocks[0].preview_rows[0], receipt);
  snapshot.block_csv_preview.csv_columns = [...new Set([...snapshot.block_csv_preview.csv_columns, ...Object.keys(receipt)])];
  snapshot.native_execution_review = { available: true, accepted: false, hashes: {
    design_sha256: "fixture-design", assembly_preview_sha256: "fixture-assembly", run_order_sha256: "fixture-order" } };
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.addInitScript(snapshot => {
    window.isTauri = true;
    window.timingAcceptCalls = [];
    window.__TAURI_INTERNALS__ = {
      convertFileSrc: file => new URL(`/packages/pps-resources/${file}`, location.origin).href,
      async invoke(command, args) {
        if (command === "designer_snapshot") return { revision: 7, snapshot: structuredClone(snapshot), capabilities: { assembly: { max_rows: 10000, max_blocks: 128 } } };
        if (command === "designer_accept_review") { window.timingAcceptCalls.push(args); snapshot.native_execution_review = { ...snapshot.native_execution_review, available: false, accepted: true }; return { accepted: true }; }
        throw new Error(`Unexpected native timing fixture command: ${command}`);
      },
    };
  }, snapshot);
  await page.goto(`${base}/apps/designer/frontend/compiled/index.html`);
  await page.waitForFunction(() => window.PPSDesignerApp?.isNative() && window.PPSDesignerApp.getState()?.native_execution_review?.available);
  assert.match(await page.locator("#native-timing-summary").innerText(), /Toolkit ITI substitution affects 1 reviewed row\./);
  assert.equal(await page.locator("#native-accept-review").isDisabled(), true);
  const details = page.locator("#block-preview-table-1 tbody tr").first().locator('td[data-label="Duration"] details');
  const summary = details.locator("summary");
  await summary.scrollIntoViewIfNeeded(); await summary.focus(); await summary.press("Enter");
  assert.equal(await details.getAttribute("open"), "");
  for (const text of ["Reported range: 1000-1500 ms", "Toolkit uniform whole-millisecond sampling", "after trial audio ends", "54419 frames", receipt.native_iti_seed_sha256]) {
    assert.ok((await details.innerText()).includes(text), text);
  }
  const geometry = [];
  for (const [width, zoom] of [[320, 1], [900, 1], [1440, 1], [1440, 2]]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(z => { document.documentElement.style.zoom = String(z); }, zoom);
    await summary.scrollIntoViewIfNeeded(); await summary.focus();
    const result = await details.evaluate(node => ({ overflow: node.scrollWidth > node.clientWidth + 1,
      seedOverflow: node.querySelector("code").scrollWidth > node.querySelector("code").clientWidth + 1,
      focused: document.activeElement === node.querySelector("summary") }));
    assert.equal(result.overflow, false, `${width}/${zoom} timing details`);
    assert.equal(result.seedOverflow, false, `${width}/${zoom} exact seed`);
    assert.equal(result.focused, true);
    await page.locator("#native-timing-summary").scrollIntoViewIfNeeded();
    const disclosure = await page.locator("#native-timing-summary").evaluate(node => ({ overflow: node.scrollWidth > node.clientWidth + 1,
      left: node.getBoundingClientRect().left, right: node.getBoundingClientRect().right, width: innerWidth }));
    assert.equal(disclosure.overflow, false); assert.ok(disclosure.left >= -1 && disclosure.right <= disclosure.width + 1);
    geometry.push({ width, zoom, ...result, disclosure });
  }
  await page.evaluate(() => { document.documentElement.style.zoom = ""; });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator("#native-timing-summary").scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(output, "native-timing-disclosure.png") });
  await summary.scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(output, "native-timing-row.png") });
  const download = page.waitForEvent("download", file => file.suggestedFilename().endsWith(".csv"));
  await page.locator("#download-block-randomization").click();
  const stream = await (await download).createReadStream(), chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const csv = Buffer.concat(chunks).toString("utf8");
  for (const field of Object.keys(receipt)) assert.ok(csv.split(/\r?\n/)[0].split(",").includes(field), field);
  assert.ok(csv.includes(receipt.native_iti_seed_sha256));
  await page.locator("#native-review-confirm").check();
  await page.locator("#native-accept-review").click();
  await page.waitForFunction(() => window.PPSDesignerApp.getState().native_execution_review.accepted);
  assert.deepEqual(await page.evaluate(() => window.timingAcceptCalls), [{ expectedRevision: 7, hashes: snapshot.native_execution_review.hashes }]);
  assert.deepEqual(errors, []);
  await writeFile(resolve(output, "native-timing-report.json"), JSON.stringify({ scope: "Real Chromium controls with mocked native IPC; no native timing qualification", geometry, acceptedExactHashes: true, csvReceiptRetained: true }, null, 2));
  await page.close();
}
