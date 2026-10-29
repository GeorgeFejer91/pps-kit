import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { writeFile } from "node:fs/promises";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PPS_PLAYWRIGHT_MODULE || "playwright");
let browser;
for (let attempt=0; attempt<40; attempt++) {
  try { browser=await chromium.connectOverCDP(process.env.PPS_DESIGNER_TEST_CDP || "http://127.0.0.1:19225"); break; }
  catch(error) { if(attempt===39 || !String(error).includes("ECONNREFUSED")) throw error; await new Promise(resolve=>setTimeout(resolve,250)); }
}
try {
  const context=browser.contexts()[0];
  const page=context.pages()[0] || await context.waitForEvent("page");
  await page.waitForURL(/^http:\/\/tauri\.localhost\//);
  page.on("dialog",dialog=>dialog.accept());
  await page.waitForFunction(()=>window.PPSDesignerApp?.getState()?.design?.name === "Native full review fixture");
  await page.locator("#edit-mode-button").click();
  await page.locator("#native-execution").scrollIntoViewIfNeeded();
  await page.locator("#native-build-review").click();
  await page.waitForFunction(()=>document.getElementById("native-cancel-work").disabled);
  assert.match(await page.locator("#native-execution-status").innerText(),/Stationary controls are missing/);
  const moving=await page.evaluate(()=>window.PPSDesignerApp.getState().design.noises.map(s=>s.prebaked_path));
  await page.locator("#native-baseline-opt-in").check();
  await page.locator("#native-baseline-source").selectOption("Pink frontal");
  await page.locator("#native-generate-baseline").click();
  await page.waitForFunction(()=>document.getElementById("native-cancel-work").disabled,null,{timeout:90_000});
  const after=await page.evaluate(()=>window.PPSDesignerApp.getState());
  assert.ok(after.design.noises[0].native_stationary_baseline_asset,await page.locator("#native-execution-status").innerText());
  assert.deepEqual(after.design.noises.map(s=>s.prebaked_path),moving);
  assert.deepEqual(after.block_csv_preview,{});
  await page.locator("#native-build-review").click();
  await page.waitForFunction(()=>document.getElementById("native-cancel-work").disabled,null,{timeout:60_000});
  const review=await page.evaluate(()=>window.PPSDesignerApp.getState());
  assert.equal(review.run_sequence_setup.csv_rows?.length,600,await page.locator("#native-execution-status").innerText());
  assert.equal(review.block_csv_preview.total_trials,204);
  assert.equal(review.native_execution_review.available,true);
  assert.equal(await page.locator("#native-accept-review").isDisabled(),true);
  assert.equal(await page.locator("#native-occurrence-table tbody tr").count(),12);
  await page.locator("#native-order-next").click();
  assert.match(await page.locator("#native-order-page").innerText(),/Page 2 of 50/);
  await page.locator("#native-review-confirm").check();
  await page.locator("#native-accept-review").click();
  await page.waitForFunction(()=>document.getElementById("native-prepare-participant").disabled === false);
  const accepted=await page.evaluate(()=>window.PPSDesignerApp.getState());
  assert.equal(accepted.native_execution_review.accepted,true);
  await page.locator("#native-execution").scrollIntoViewIfNeeded();
  await page.locator("#native-execution").screenshot({path:"artifacts/ui-workflow-check/native-assembly-review.png"});
  await page.setViewportSize({width:900,height:720});
  await page.waitForFunction(()=>[...document.querySelectorAll("#native-execution button")].filter(button=>button.getClientRects().length).every(button=>button.dataset.pretextResult && button.dataset.pretextResult !== "unavailable"));
  const geometry=await page.locator("#native-execution").evaluate(panel=>({
    overflows:[...panel.querySelectorAll("button, input, select")].filter(element=>element.getClientRects().length && (element.scrollWidth>element.clientWidth+2 || element.getBoundingClientRect().right>panel.getBoundingClientRect().right+2)).map(element=>element.id),
    measured:[...panel.querySelectorAll("button")].filter(element=>element.getClientRects().length).map(element=>({id:element.id,result:element.dataset.pretextResult,size:element.dataset.pretextFontSize})),
  }));
  assert.deepEqual(geometry.overflows,[]);
  // Editing a draft ingredient revokes the native acceptance before a replacement generation.
  await page.locator("#movement-duration").fill("1.25");
  assert.equal(await page.locator("#native-prepare-participant").isDisabled(),true);
  assert.equal(await page.evaluate(()=>window.PPSDesignerApp.getState().native_execution_review),null);
  await writeFile("artifacts/ui-workflow-check/native-assembly-report.json",JSON.stringify({actualNativeBaseline:true,movingAudioPreserved:true,fullTrials:204,fullOccurrences:600,pagedReview:true,explicitAcceptance:true,editRevokesAcceptance:true,geometry,physicalTimingQualified:false},null,2));
  console.log("Native WebView: actual stationary control, full 204-trial/600-occurrence review, explicit acceptance and edit invalidation passed.");
} finally { await browser.close(); }
