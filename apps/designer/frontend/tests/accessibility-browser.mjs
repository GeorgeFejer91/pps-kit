import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
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
  const audioBytes = Buffer.alloc(44 + 4410 * 2);
  audioBytes.write("RIFF", 0); audioBytes.writeUInt32LE(audioBytes.length - 8, 4);
  audioBytes.write("WAVEfmt ", 8); audioBytes.writeUInt32LE(16, 16);
  audioBytes.writeUInt16LE(1, 20); audioBytes.writeUInt16LE(1, 22);
  audioBytes.writeUInt32LE(44100, 24); audioBytes.writeUInt32LE(88200, 28);
  audioBytes.writeUInt16LE(2, 32); audioBytes.writeUInt16LE(16, 34);
  audioBytes.write("data", 36); audioBytes.writeUInt32LE(audioBytes.length - 44, 40);
  for (let i = 0; i < 4410; i++) audioBytes.writeInt16LE(Math.round(500 * Math.sin(i / 20)), 44 + i * 2);
  const audioHash = createHash("sha256").update(audioBytes).digest("hex");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Load audio for Before experiment", exact: true }).click();
  await (await chooser).setFiles({ name: "New-instruction.wav", mimeType: "audio/wav", buffer: audioBytes });
  await page.waitForFunction(hash => window.PPSDesignerApp.getState().design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots
    .some(slot => slot.slot === "before_experiment" && slot.path === `browser-asset:${hash}.wav`), audioHash);
  assert.equal(await page.locator('[data-run-instruction-slot="before_experiment"] [data-instruction-field="path"]').inputValue(), `browser-asset:${audioHash}.wav`, "the instruction form adopts the selected file before later edits");
  assert.match(await page.locator('[data-run-instruction-slot="before_experiment"] .status-label').innerText(), /duration unverified/);
  // Real file selection and IndexedDB writes, with only completion order controlled.
  await page.evaluate(() => {
    window.originalAudioStore = window.PPSDesigner.drafts.storeAudio;
    window.pendingAudioStores = {};
    window.revokedImportUrls = [];
    window.originalRevokeObjectURL = URL.revokeObjectURL;
    URL.revokeObjectURL = url => { window.revokedImportUrls.push(url); window.originalRevokeObjectURL.call(URL, url); };
    window.PPSDesigner.drafts.storeAudio = async file => {
      const stored = await window.originalAudioStore(file);
      await new Promise(resolve => { window.pendingAudioStores[file.name] = { resolve, url: stored.url }; });
      return stored;
    };
  });
  const olderBytes = Buffer.from(audioBytes);
  olderBytes.writeInt16LE(1234, 44);
  const firstChooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Load audio for Before experiment", exact: true }).click();
  await (await firstChooser).setFiles({ name: "Superseded.wav", mimeType: "audio/wav", buffer: olderBytes });
  await page.waitForFunction(() => window.pendingAudioStores["Superseded.wav"]);
  const latestChooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Load audio for Before experiment", exact: true }).click();
  await (await latestChooser).setFiles({ name: "Latest-instruction.wav", mimeType: "audio/wav", buffer: audioBytes });
  await page.waitForFunction(() => window.pendingAudioStores["Latest-instruction.wav"]);
  await page.getByRole("combobox", { name: "Before experiment continue mode", exact: true }).press("Enter");
  await page.getByRole("option", { name: "Runner button", exact: true }).waitFor();
  await page.evaluate(() => window.pendingAudioStores["Latest-instruction.wav"].resolve());
  await page.waitForFunction(() => window.revokedImportUrls.includes(window.pendingAudioStores["Latest-instruction.wav"].url));
  assert.equal(await page.locator("#bounded-select-menu").isVisible(), false, "a changed instruction profile closes the replaced select's menu");
  assert.equal(await instruction.inputValue(), "Latest-instruction");
  await page.evaluate(() => window.pendingAudioStores["Superseded.wav"].resolve());
  await page.waitForFunction(() => window.revokedImportUrls.includes(window.pendingAudioStores["Superseded.wav"].url));
  assert.equal(await page.locator('[data-run-instruction-slot="before_experiment"] [data-instruction-field="path"]').inputValue(), `browser-asset:${audioHash}.wav`);
  await page.evaluate(() => {
    window.PPSDesigner.drafts.storeAudio = window.originalAudioStore;
    URL.revokeObjectURL = window.originalRevokeObjectURL;
  });
  await instruction.fill("Reviewed instruction label");
  await page.waitForFunction(() => window.PPSDesignerApp.getState().design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots.find(slot => slot.slot === "before_experiment").label === "Reviewed instruction label");
  await page.waitForFunction(() => document.activeElement === document.getElementById("instruction-before_experiment-label"));
  const continuation = page.getByRole("combobox", { name: "Before experiment continue mode", exact: true });
  await page.evaluate(() => {
    window.sameProfileRenderCount = 0;
    window.sameProfileObserver = new MutationObserver(() => window.sameProfileRenderCount++);
    window.sameProfileObserver.observe(document.getElementById("run-sequence-summary"), { childList: true });
  });
  await continuation.press("Enter"); // Blurring the edited label schedules another identical preview.
  await page.waitForFunction(() => window.sameProfileRenderCount > 0);
  await page.evaluate(() => window.sameProfileObserver.disconnect());
  await page.getByRole("option", { name: "Runner button", exact: true }).click();
  await page.waitForFunction(() => window.PPSDesignerApp.getState().design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots.find(slot => slot.slot === "before_experiment").continue_mode === "button");
  await page.waitForFunction(() => document.activeElement === document.getElementById("instruction-before_experiment-continue-combobox"));
  const delay = page.getByRole("spinbutton", { name: "Before experiment delay seconds", exact: true });
  await delay.fill("2.5");
  await page.waitForFunction(() => window.PPSDesignerApp.getState().design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots.find(slot => slot.slot === "before_experiment").delay_s === 2.5);
  const focusEvidence = [];
  for (const height of [620, 1000]) {
    await page.setViewportSize({ width: 1440, height });
    const ids = ["enabled", "label", "import", "continue-combobox", "delay", "button"].map(field => `instruction-after_experiment-${field}`);
    await page.locator(`#${ids[0]}`).focus();
    for (let i = 0; i < ids.length; i++) {
      if (i) await page.keyboard.press("Tab");
      assert.equal(await page.evaluate(() => document.activeElement.id), ids[i]);
      await page.waitForFunction(() => {
        const box = document.activeElement.getBoundingClientRect();
        return box.top >= 0 && box.bottom <= innerHeight;
      });
      await page.evaluate(async () => {
        let previous = NaN, stable = 0;
        for (let frame = 0; frame < 180 && stable < 3; frame++) {
          await new Promise(requestAnimationFrame);
          const top = document.activeElement.getBoundingClientRect().top;
          stable = Math.abs(top - previous) < 0.1 ? stable + 1 : 0;
          previous = top;
        }
      });
      const visible = await page.evaluate(() => {
        const node = document.activeElement, box = node.getBoundingClientRect();
        const hit = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
        const footer = document.querySelector("#save-study-profile").closest(".step-footer").getBoundingClientRect();
        return { visible: Boolean(hit && (node === hit || node.contains(hit))) && box.top >= 0 && box.bottom <= innerHeight
          && (box.bottom <= footer.top || box.top >= footer.bottom), box: box.toJSON(), footer: footer.toJSON() };
      });
      focusEvidence.push({ height, id: ids[i], ...visible });
      if (!visible.visible) await page.screenshot({ path: `${screenshotPath}-focus-${height}.png` });
      assert.equal(visible.visible, true, `${ids[i]} is fully above the footer at ${height}px: ${JSON.stringify(visible)}`);
    }
  }
  await writeFile(join(dirname(screenshotPath), "instruction-focus.json"), JSON.stringify(focusEvidence, null, 2));
  await page.locator("#run-instruction-slots").screenshot({ path: screenshotPath });
  await page.locator("#save-study-profile").click();
  await page.waitForFunction(async () => (await window.PPSDesigner.drafts.load())?.custom_workflow.is_finalized);
  assert.equal(await instruction.isDisabled(), true, "finalization replaces the identical profile with disabled controls");
  await page.reload();
  await page.waitForFunction(() => window.PPSDesignerApp?.getState()?.custom_workflow.is_finalized);
  const download = page.waitForEvent("download");
  await page.locator("#export-profile-bundle").click();
  const file = await download;
  const path = join(dirname(screenshotPath), "accessible-instructions.pps-profile");
  await file.saveAs(path);
  const bytes = await readFile(path);
  let profile;
  const entries = new Map();
  for (let offset = 0; bytes.readUInt32LE(offset) === 0x04034b50;) {
    assert.equal(bytes.readUInt16LE(offset + 8), 0, "the existing bundle stores entries uncompressed");
    const size = bytes.readUInt32LE(offset + 18), nameSize = bytes.readUInt16LE(offset + 26), extraSize = bytes.readUInt16LE(offset + 28);
    const start = offset + 30 + nameSize + extraSize;
    const name = bytes.toString("utf8", offset + 30, offset + 30 + nameSize);
    entries.set(name, bytes.subarray(start, start + size));
    if (name === "profile.json") profile = JSON.parse(bytes.toString("utf8", start, start + size));
    offset = start + size;
  }
  const slot = profile.design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots.find(slot => slot.slot === "before_experiment");
  assert.equal(slot.label, "Reviewed instruction label");
  assert.equal(slot.continue_mode, "button");
  assert.equal(slot.delay_s, 2.5);
  assert.equal(slot.path, `browser-asset:${audioHash}.wav`);
  assert.equal(slot.sha256, audioHash);
  assert.equal(slot.browser_asset_id, `${audioHash}.wav`);
  const asset = profile.assets.find(asset => asset.logical_id === slot.browser_asset_id);
  assert.equal(asset.source_name, "Latest-instruction.wav");
  assert.equal(asset.sha256, audioHash);
  assert.deepEqual(entries.get(asset.path), audioBytes);
  const manifest = JSON.parse(entries.get("manifest.json").toString("utf8"));
  assert.equal(manifest.files.find(file => file.path === asset.path).sha256, audioHash);
}
