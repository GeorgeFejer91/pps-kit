import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";

export async function verifyRunnerNavigation(page) {
  const control = page.getByRole("button", { name: "Experiment Control", exact: true });
  const logging = page.getByRole("button", { name: "Data Logging", exact: true });
  const remote = page.getByRole("button", { name: "Phone Remote", exact: true });
  await control.focus();
  assert.equal(await control.getAttribute("aria-current"), "page");
  await page.keyboard.press("Tab");
  assert.equal(await logging.evaluate(node => node === document.activeElement), true);
  await page.keyboard.press("Enter");
  assert.equal(await logging.getAttribute("aria-current"), "page");
  assert.equal(await control.getAttribute("aria-current"), null);
  assert.equal(await page.locator("#runner-logging").isVisible(), true);
  assert.equal(await page.locator("#runner-control").isVisible(), false);
  await page.keyboard.press("Tab");
  assert.equal(await remote.evaluate(node => node === document.activeElement), true);
  await page.keyboard.press("Space");
  assert.equal(await remote.getAttribute("aria-current"), "page");
  assert.equal(await page.locator("nav [aria-selected]").count(), 0);
  for (const width of [320, 768, 1440, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const button of [control, logging, remote]) {
      assert.equal(await button.evaluate(node => { const box = node.getBoundingClientRect(); return box.left >= -1 && box.right <= innerWidth + 1 && node.scrollWidth <= node.clientWidth + 1; }), true);
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => document.documentElement.style.zoom = "2");
  assert.equal(await remote.evaluate(node => node.getBoundingClientRect().right <= innerWidth + 1), true);
  await page.evaluate(() => document.documentElement.style.zoom = "");
  await control.click();
}

export async function verifyDesignerControlNames(page, screenshotPath) {
  await page.waitForFunction(() => window.PPSDesignerApp?.getState()?.design);
  await page.evaluate(() => {
    const s = window.PPSDesignerApp.getState();
    window.accessibilityInitialState = structuredClone(s);
    s.design.name = "Accessible control regression";
    s.design.study_profile_id = ""; s.design.study_profile_title = "";
    Object.assign(s.design.study_profile_reference_parameters, { dashboard_mode: "custom", profile_status: "draft" });
    delete s.design.study_profile_reference_parameters.designer_progress;
    s.custom_workflow = { ...s.custom_workflow, is_custom: true, is_finalized: false,
      edit_step: "trials", confirmed_steps: ["study", "stimulus"], needs_review_steps: [] };
    s.design.protocol.trial_strips = [{ label: "Long condition: approaching sound before and after instruction",
      elements: [{ kind: "jitter", label: "Delay", jitter_values_ms: [0, 50] }] }];
    window.PPSDesignerApp.restoreHostedDraft(s);
  });
  await page.locator("#edit-mode-button").click();
  const condition = page.getByRole("textbox", { name: "Condition label", exact: true });
  const jitter = page.getByRole("textbox", { name: "Jitter values ms", exact: true });
  assert.equal(await condition.count(), 1);
  assert.equal(await jitter.count(), 1);
  await condition.focus();
  await page.keyboard.press("Tab");
  assert.equal(await page.getByRole("button", { name: "Remove event", exact: true }).evaluate(node => node === document.activeElement), true);
  await page.keyboard.press("Tab");
  const mode = page.getByRole("checkbox", { name: "Jitter / ITI box", exact: true });
  assert.equal(await mode.evaluate(node => node === document.activeElement), true);
  await page.keyboard.press("Space"); // Rebuilds this event as an audio box.
  assert.equal(await page.locator("#trial-0-event-0-mode").evaluate(node => node === document.activeElement), true);
  await page.keyboard.press("Space"); // Rebuilds it as a jitter event again.
  await page.keyboard.press("Tab");
  assert.equal(await jitter.evaluate(node => node === document.activeElement), true);
  assert.notEqual(await jitter.evaluate(node => getComputedStyle(node).outlineStyle), "none");
  const help = page.locator('[data-segment-info="trials"]');
  await help.focus(); await page.keyboard.press("Enter");
  await page.locator("#segment-info-modal-close").waitFor({ state: "visible" });
  await page.waitForFunction(() => document.activeElement?.id === "segment-info-modal-close");
  await page.keyboard.press("Escape");
  assert.equal(await help.evaluate(node => node === document.activeElement), true);
  for (const width of [320, 768, 1440, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    await jitter.scrollIntoViewIfNeeded();
    const fit = await jitter.evaluate(node => { const box = node.getBoundingClientRect(); return box.left >= -1 && box.right <= innerWidth + 1; });
    assert.equal(fit, true, `Jitter control reflows at ${width}px`);
    assert.equal(await condition.getAttribute("id"), "trial-condition-0");
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => document.documentElement.style.zoom = "2");
  await jitter.scrollIntoViewIfNeeded();
  assert.equal(await jitter.evaluate(node => node.getBoundingClientRect().right <= innerWidth + 1), true);
  await page.evaluate(() => document.documentElement.style.zoom = "");
  await page.evaluate(() => {
    const s = structuredClone(window.accessibilityInitialState);
    s.design.study_profile_id = ""; s.design.study_profile_title = "";
    Object.assign(s.design.study_profile_reference_parameters, { dashboard_mode: "custom", profile_status: "draft" });
    delete s.design.study_profile_reference_parameters.designer_progress;
    Object.assign(s.custom_workflow, { is_custom: true, is_finalized: false, edit_step: "run",
      confirmed_steps: ["study", "stimulus", "trials", "baseline", "block", "schedule"], needs_review_steps: [] });
    window.PPSDesignerApp.restoreHostedDraft(s);
  });
  await page.locator("#edit-mode-button").click();
  await page.locator(".run-instructions-panel > summary").click();
  const instruction = page.getByRole("textbox", { name: "Before experiment audio label", exact: true });
  assert.equal(await instruction.count(), 1);
  assert.equal(await page.getByRole("combobox", { name: "Before experiment continue mode", exact: true }).count(), 1);
  assert.equal(await page.getByRole("spinbutton", { name: "Before experiment delay seconds", exact: true }).count(), 1);
  await instruction.fill("Reviewed instruction label");
  await page.waitForFunction(() => window.PPSDesignerApp.getState().design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots[0].label === "Reviewed instruction label");
  await page.waitForFunction(() => document.activeElement === document.getElementById("instruction-before_experiment-label"));
  const continuation = page.getByRole("combobox", { name: "Before experiment continue mode", exact: true });
  await continuation.press("Enter");
  await page.getByRole("option", { name: "Runner button", exact: true }).click();
  await page.waitForFunction(() => window.PPSDesignerApp.getState().design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots[0].continue_mode === "button");
  await page.waitForFunction(() => document.activeElement === document.getElementById("instruction-before_experiment-continue-combobox"));
  const delay = page.getByRole("spinbutton", { name: "Before experiment delay seconds", exact: true });
  await delay.fill("2.5");
  await page.waitForFunction(() => window.PPSDesignerApp.getState().design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots[0].delay_s === 2.5);
  await page.locator("#run-instruction-slots").screenshot({ path: screenshotPath });
  await page.locator("#save-study-profile").click();
  await page.waitForFunction(async () => (await window.PPSDesigner.drafts.load())?.custom_workflow.is_finalized);
  await page.reload();
  await page.waitForFunction(() => window.PPSDesignerApp?.getState()?.custom_workflow.is_finalized);
  const download = page.waitForEvent("download");
  await page.locator("#export-profile-bundle").click();
  const file = await download;
  const path = join(dirname(screenshotPath), "accessible-instructions.pps-profile");
  await file.saveAs(path);
  const bytes = await readFile(path);
  let profile;
  for (let offset = 0; bytes.readUInt32LE(offset) === 0x04034b50;) {
    assert.equal(bytes.readUInt16LE(offset + 8), 0, "the existing bundle stores entries uncompressed");
    const size = bytes.readUInt32LE(offset + 18), nameSize = bytes.readUInt16LE(offset + 26), extraSize = bytes.readUInt16LE(offset + 28);
    const start = offset + 30 + nameSize + extraSize;
    if (bytes.toString("utf8", offset + 30, offset + 30 + nameSize) === "profile.json") profile = JSON.parse(bytes.toString("utf8", start, start + size));
    offset = start + size;
  }
  const slot = profile.design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots[0];
  assert.equal(slot.label, "Reviewed instruction label");
  assert.equal(slot.continue_mode, "button");
  assert.equal(slot.delay_s, 2.5);
}
