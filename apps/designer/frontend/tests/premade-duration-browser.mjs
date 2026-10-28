import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";

export async function verifyPremadeDuration(browser, base, output) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("dialog", dialog => dialog.type() === "confirm" ? dialog.accept() : dialog.dismiss());
  const id = "canzoneri_2012_dynamic_sounds";
  await page.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1&template=${id}`);
  await page.waitForFunction(id => window.PPSDesignerApp?.getState()?.design?.study_profile_id === id, id);
  const inspect = async () => {
    const snapshot = await page.evaluate(() => window.PPSDesignerApp.getState());
    const sources = [...snapshot.design.noises, ...snapshot.design.custom_looming_files];
    assert.ok(sources.length >= 2);
    assert.ok(sources.every(source => source.duration_s === 3), "both selected premade directions retain actual duration");
    assert.ok(snapshot.trial_file_bake.files.length > 0);
    assert.ok(snapshot.trial_file_bake.files.every(file => file.duration_ms === 5000), "3 s audio plus existing 1 s prefix/suffix");
    const rows = snapshot.block_csv_preview.blocks.flatMap(block => block.preview_rows);
    assert.ok(rows.length > 0);
    assert.ok(snapshot.block_csv_preview.blocks.every(block => block.preview_rows.length === block.trial_count));
    assert.ok(rows.every(row => row.duration_ms === 5000));
    return snapshot;
  };
  const initial = await inspect();
  await page.locator("#edit-mode-button").click();
  await page.locator("#customize-study-name").fill("Premade duration control regression");
  await page.locator("#customize-submit").click();
  await page.locator("#customize-modal").waitFor({ state: "hidden" });
  await page.waitForFunction(() => window.PPSDesignerApp.getState().custom_workflow?.edit_step === "stimulus");
  await page.locator('[data-continue-step="stimulus"]').click();
  await page.waitForFunction(() => window.PPSDesignerApp.getState().custom_workflow?.edit_step === "trials");
  await page.locator('[data-continue-step="trials"]').click();
  await page.waitForFunction(() => window.PPSDesignerApp.getState().custom_workflow?.edit_step === "baseline");
  await page.locator('[data-continue-step="baseline"]').click();
  await page.waitForFunction(() => window.PPSDesignerApp.getState().custom_workflow?.edit_step === "block");
  await page.locator('[data-continue-step="block"]').click();
  await page.locator("#accept-block-csvs").click();
  await page.locator("#save-study-profile").click();
  await page.waitForFunction(() => window.PPSDesignerApp.getState().custom_workflow.is_finalized);
  const finalized = await inspect();
  assert.equal(finalized.block_csv_preview.total_count, initial.block_csv_preview.total_count);
  const downloadEvent = page.waitForEvent("download");
  await page.locator("#export-profile-bundle").click();
  const download = await downloadEvent;
  await download.saveAs(resolve(output, "canzoneri-duration.pps-profile"));
  assert.equal(await download.failure(), null);
  await writeFile(resolve(output, "canzoneri-duration-plan.json"), JSON.stringify({
    design: finalized.design, block_csv_preview: finalized.block_csv_preview,
    variants: await page.evaluate(() => window.PPSDesignerApp.getAssemblyVariants()),
    run_sequence_setup: finalized.run_sequence_setup, participant_orders: finalized.participant_orders,
  }, null, 2));
  await page.screenshot({ path: resolve(output, "canzoneri-duration-finalized.png") });
  assert.deepEqual(errors, []);
  await page.close();
}
