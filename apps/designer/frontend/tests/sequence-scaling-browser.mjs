import assert from "node:assert/strict";

// Uses the normal hosted restore, edit and Save & Continue routes, including IndexedDB.
export async function verifySequenceScaling(page) {
  await page.waitForFunction(() => window.PPSDesignerApp?.getState()?.design);
  await page.evaluate(() => {
    const s = window.PPSDesignerApp.getState();
    s.design.name = "Sequence scaling regression";
    s.design.study_profile_id = ""; s.design.study_profile_title = "";
    Object.assign(s.design.study_profile_reference_parameters, { dashboard_mode: "custom", profile_status: "draft" });
    delete s.design.study_profile_reference_parameters.designer_progress;
    s.custom_workflow = { ...s.custom_workflow, is_custom: true, is_finalized: false,
      edit_step: "trials", confirmed_steps: ["study", "stimulus"], needs_review_steps: [] };
    const audio = s.design.protocol.trial_strips[0].elements.at(-1);
    s.design.protocol.trial_strips = [{ strip_id: "scaling", label: "Six-by-six", audio_tactile_percentage: 100,
      baseline_percentage: 0, catch_percentage: 0, elements: [
        ...Array.from({ length: 6 }, (_, i) => ({ element_id: `delay-${i}`, kind: "jitter",
          label: `Delay ${i + 1}`, jitter_values_ms: [0, 50, 100, 150, 200, 250] })),
        { ...audio, source_labels: [audio.source_labels[0]] },
      ] }];
    window.PPSDesignerApp.restoreHostedDraft(s);
  });
  await page.locator("#edit-mode-button").click();
  await page.locator('[data-element-field="jitter_values_ms"]').first().fill("0, 50, 100, 150, 200, 300");
  assert.equal(await page.locator(".filmstrip-row-variant-count").innerText(), "46656 variants");
  await page.locator('[data-continue-step="trials"]').click();
  await page.waitForFunction(async () => (await window.PPSDesigner.drafts.load())?.design.protocol.trial_strips[0].elements[0].jitter_values_ms.at(-1) === 300);
  await page.evaluate(async () => window.PPSDesignerApp.restoreHostedDraft(await window.PPSDesigner.drafts.load()));
  assert.equal(await page.locator(".filmstrip-row-variant-count").innerText(), "46656 variants");
  await page.evaluate(() => {
    const s = window.PPSDesignerApp.getState();
    delete s.design.study_profile_reference_parameters.designer_progress;
    Object.assign(s.custom_workflow, { edit_step: "trials", confirmed_steps: ["study", "stimulus"] });
    s.design.protocol.trial_strips[0].elements = Array.from({ length: 54 }, (_, i) => ({
      element_id: `overflow-${i}`, kind: "jitter", label: `Delay ${i + 1}`, jitter_values_ms: [0, 1],
    }));
    window.PPSDesignerApp.restoreHostedDraft(s);
  });
  assert.match(await page.locator(".filmstrip-row-variant-count").innerText(), /Too many variants/);
  await page.locator("#edit-mode-button").click();
  await page.locator('[data-element-field="jitter_values_ms"]').first().fill("0, 2");
  await page.locator('[data-continue-step="trials"]').click();
  await page.waitForFunction(() => document.querySelector("#toast").textContent.includes("draft is preserved"));
  const saved = await page.evaluate(async () => {
    const s = await window.PPSDesigner.drafts.load();
    return { elements: s.design.protocol.trial_strips[0].elements, step: s.custom_workflow.steps.find(step => step.id === "trials") };
  });
  assert.equal(saved.elements.length, 54);
  assert.deepEqual(saved.elements[0].jitter_values_ms, [0, 2]);
  assert.equal(saved.step.complete, false);
  await page.evaluate(async () => window.PPSDesignerApp.restoreHostedDraft(await window.PPSDesigner.drafts.load()));
  assert.match(await page.locator(".filmstrip-row-variant-count").innerText(), /Too many variants/);
}
