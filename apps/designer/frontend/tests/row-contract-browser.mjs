import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { trialFamilyContract, rowContractMetadata, ROW_CONTRACT_FIELDS } from "../row_contract.js";

export async function verifySavedRowContracts(browser, base, output) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const id = "tajadura_jimenez_2009_uncrossed_visual_deprivation";
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("dialog", dialog => dialog.type() === "confirm" ? dialog.accept() : dialog.dismiss());
  await page.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1&template=${id}`);
  await page.waitForFunction(id => window.PPSDesignerApp?.getState()?.design?.study_profile_id === id, id);
  const inspect = async () => {
    const snapshot = await page.evaluate(() => window.PPSDesignerApp.getState());
    const rows = snapshot.block_csv_preview.blocks.flatMap(block => block.preview_rows);
    assert.equal(rows.length, 300);
    assert.ok(ROW_CONTRACT_FIELDS.every(field => snapshot.block_csv_preview.csv_columns.includes(field)));
    for (const row of [...snapshot.trial_file_bake.files, ...snapshot.trial_pool_bake.preview_rows, ...rows]) {
      const strip = snapshot.design.protocol.trial_strips.find(strip => strip.label === row.row_label);
      assert.ok(strip?.metadata, "edited strip retains its existing saved contract");
      assert.deepEqual(rowContractMetadata(row), trialFamilyContract(strip.metadata, row.family));
      assert.equal(row.response_choice_set, "left,right");
      assert.equal(row.iti_ms, "1950");
      assert.equal(row.expected_response, "respond");
    }
    assert.deepEqual(new Set(rows.map(row => row.correct_response)), new Set(["left", "right"]));
    return snapshot;
  };
  await inspect();
  await page.locator("#edit-mode-button").click();
  await page.locator("#customize-study-name").fill("Saved row contract control regression");
  await page.locator("#customize-submit").click();
  await page.locator("#customize-modal").waitFor({ state: "hidden" });
  await page.waitForFunction(() => window.PPSDesignerApp.getState().custom_workflow?.edit_step === "stimulus");
  await page.locator('[data-continue-step="stimulus"]').click();
  await page.waitForFunction(() => window.PPSDesignerApp.getState().custom_workflow?.edit_step === "trials");
  await page.locator('[data-strip-field="label"]').first().fill("Reviewed external left");
  await page.locator('[data-continue-step="trials"]').click();
  await page.waitForFunction(() => window.PPSDesignerApp.getState().custom_workflow?.edit_step === "baseline");
  await page.locator('[data-continue-step="baseline"]').click();
  await page.waitForFunction(() => window.PPSDesignerApp.getState().custom_workflow?.edit_step === "block");
  await page.locator('[data-continue-step="block"]').click();
  await page.locator("#accept-block-csvs").click();
  await page.locator("#save-study-profile").click();
  await page.waitForFunction(() => window.PPSDesignerApp.getState().custom_workflow.is_finalized);
  await inspect();
  await page.reload();
  await page.waitForFunction(() => {
    const snapshot = window.PPSDesignerApp?.getState();
    return snapshot?.custom_workflow?.is_custom && snapshot.custom_workflow.is_finalized
      && snapshot.design.protocol.trial_strips[0].label === "Reviewed external left";
  });
  const snapshot = await inspect();
  assert.equal(snapshot.design.protocol.trial_strips[0].label, "Reviewed external left");
  const csvEvent = page.waitForEvent("download", file => file.suggestedFilename().endsWith(".csv"));
  await page.locator("#download-block-randomization").click();
  const csvDownload = await csvEvent;
  const csvPath = resolve(output, "row-contract-block.csv");
  await csvDownload.saveAs(csvPath);
  const csv = await readFile(csvPath, "utf8");
  assert.match(csv.split(/\r?\n/)[0], /response_choice_set,correct_response/);
  assert.match(csv, /"left,right",left/);
  assert.match(csv, /"left,right",right/);
  const bundleEvent = page.waitForEvent("download", file => file.suggestedFilename().endsWith(".pps-profile"));
  await page.locator("#export-profile-bundle").click();
  const bundlePath = resolve(output, "row-contract.pps-profile");
  await (await bundleEvent).saveAs(bundlePath);
  const bytes = await readFile(bundlePath);
  let profile;
  for (let offset = 0; bytes.readUInt32LE(offset) === 0x04034b50;) {
    assert.equal(bytes.readUInt16LE(offset + 8), 0, "the existing portable bundle stores uncompressed entries");
    const size = bytes.readUInt32LE(offset + 18), nameSize = bytes.readUInt16LE(offset + 26), extra = bytes.readUInt16LE(offset + 28);
    const start = offset + 30 + nameSize + extra;
    if (bytes.toString("utf8", offset + 30, offset + 30 + nameSize) === "profile.json") profile = JSON.parse(bytes.toString("utf8", start, start + size));
    offset = start + size;
  }
  assert.deepEqual(profile.design.protocol.trial_strips, snapshot.design.protocol.trial_strips);
  await writeFile(resolve(output, "row-contract-plan.json"), JSON.stringify({
    design: snapshot.design, block_csv_preview: snapshot.block_csv_preview,
    variants: await page.evaluate(() => window.PPSDesignerApp.getAssemblyVariants()),
    run_sequence_setup: snapshot.run_sequence_setup,
  }, null, 2));
  assert.deepEqual(errors, []);
  await page.close();
}
