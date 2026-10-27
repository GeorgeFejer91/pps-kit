import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PPS_PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../../../", import.meta.url));
const output = resolve(root, "artifacts/ui-workflow-check");
await mkdir(output, { recursive: true });
const types = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".wav": "audio/wav", ".woff2": "font/woff2" };
const server = createServer(async (request, response) => {
  let path = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  if (path.startsWith("/assets/preloads/")) path = `/packages/pps-resources${path}`;
  if (path.startsWith("/study_templates/")) path = `/packages/pps-resources${path}`;
  const target = resolve(root, `.${path}`);
  if (!target.startsWith(root.endsWith(sep) ? root : root + sep)) { response.writeHead(403).end(); return; }
  try { response.writeHead(200, { "Content-Type": types[extname(target)] || "application/octet-stream" }).end(await readFile(target)); }
  catch { response.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, "127.0.0.1", done));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true });
const report = { browser: browser.version(), checks: [] };
try {
  const runner = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  runner.on("pageerror", error => errors.push(error.message));
  await runner.goto(`${base}/apps/runner/compiled/index.html`);
  await runner.locator("#state-chip").filter({ hasText: "Idle" }).waitFor();
  await runner.getByLabel("Participant code", { exact: true }).fill("LOCAL-002");
  await runner.getByLabel("Age", { exact: true }).fill("38");
  await runner.locator("#participant-handedness").selectOption("left");
  await runner.locator("#participant-gender").selectOption("prefer_not_to_say");
  await runner.locator("#participant-name").fill("Local test participant");
  await runner.locator("#name-sharing").check();
  for (let index = 0; index < 3; index++) {
    await runner.getByRole("button", { name: "Refresh snapshot", exact: true }).click();
    await runner.waitForFunction(() => document.getElementById("last-note").textContent !== "");
  }
  assert.equal(await runner.locator("#participant-code").inputValue(), "LOCAL-002");
  assert.equal(await runner.locator("#participant-age").inputValue(), "38");
  assert.equal(await runner.locator("#participant-handedness").inputValue(), "left");
  assert.equal(await runner.locator("#participant-gender").inputValue(), "prefer_not_to_say");
  assert.equal(await runner.locator("#name-sharing").isChecked(), true);
  await runner.locator("#setup-form").screenshot({ path: resolve(output, "runner-draft.png") });
  await runner.getByRole("button", { name: "Submit participant setup", exact: true }).click();
  await runner.locator("#setup-badge").filter({ hasText: /^Ready$/ }).waitFor();
  assert.equal(await runner.locator("#participant-chip").innerText(), "LOCAL-002");
  assert.deepEqual(errors, []);
  report.checks.push("Runner draft survives snapshot refresh and acknowledged submit");

  const designer = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  designer.on("pageerror", error => errors.push(error.message));
  await designer.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1&desktop=1`);
  await designer.waitForFunction(() => window.PPSDesignerApp?.getState()?.design);
  await designer.evaluate(async () => {
    const snapshot = window.PPSDesignerApp.getState();
    snapshot.design.name = "Browser finalization regression";
    snapshot.design.study_profile_id = "";
    snapshot.design.study_profile_title = "";
    snapshot.design.study_profile_reference_parameters.dashboard_mode = "custom";
    snapshot.design.study_profile_reference_parameters.profile_status = "draft";
    snapshot.custom_workflow = { ...snapshot.custom_workflow, is_custom: true, is_finalized: false,
      edit_step: "run", confirmed_steps: ["study", "stimulus", "trials", "baseline", "block", "schedule"], needs_review_steps: [] };
    snapshot.project = { ...snapshot.project, project_id: "browser-regression", project_kind: "browser_draft" };
    window.PPSDesignerApp.restoreHostedDraft(snapshot);
    window.realDraftSave = window.PPSDesigner.drafts.save;
    window.PPSDesigner.drafts.save = async () => { throw new Error("Storage quota test failure"); };
  });
  const previewFixture = await designer.evaluate(() => window.PPSDesignerApp.getState());
  await designer.locator("#edit-mode-button").click();
  await designer.locator("#save-study-profile").click();
  await designer.waitForFunction(() => document.getElementById("toast").textContent.includes("Storage quota test failure"));
  assert.equal(await designer.evaluate(() => window.PPSDesignerApp.getState().custom_workflow.is_finalized), false);
  assert.equal(await designer.locator("#save-study-profile").isEnabled(), true);
  assert.equal(await designer.locator("#edit-mode-button").getAttribute("aria-checked"), "true");
  await designer.locator("section").filter({ has: designer.locator("#save-study-profile") }).last()
    .screenshot({ path: resolve(output, "designer-save-failure.png") });
  await designer.evaluate(() => {
    window.PPSDesigner.drafts.save = async snapshot => {
      await new Promise(done => { window.finishDraftSave = done; });
      await window.realDraftSave(snapshot);
    };
  });
  await designer.locator("#save-study-profile").click();
  await designer.waitForFunction(() => typeof window.finishDraftSave === "function");
  const pendingCount = await designer.locator("#participants").inputValue();
  assert.equal(await designer.evaluate(() => document.querySelector(".app-shell").inert), true);
  assert.equal(await designer.evaluate(() => window.PPSDesignerApp.restoreHostedDraft({ design: { name: "Other project" } })), false);
  await designer.locator("#participants").focus();
  await designer.keyboard.type("99");
  assert.equal(await designer.locator("#participants").inputValue(), pendingCount);
  await designer.evaluate(() => window.finishDraftSave());
  await designer.waitForFunction(() => window.PPSDesignerApp.getState().custom_workflow.is_finalized);
  assert.equal(await designer.evaluate(() => document.querySelector(".app-shell").inert), false);
  assert.equal(await designer.evaluate(async () => (await window.PPSDesigner.drafts.load()).custom_workflow.is_finalized), true);
  assert.equal(await designer.locator("#edit-mode-button").getAttribute("aria-checked"), "false");
  const downloadPromise = designer.waitForEvent("download");
  await designer.locator("#export-profile-bundle").click();
  const download = await downloadPromise;
  await download.saveAs(resolve(output, "browser-finalized.pps-profile"));
  assert.equal(await download.failure(), null);
  await designer.locator("section").filter({ has: designer.locator("#export-profile-bundle") }).last()
    .screenshot({ path: resolve(output, "designer-locked-export.png") });
  report.checks.push("Designer storage rejection stays editable; retry persists lock and exports bundle");
  report.text = await designer.locator("#export-profile-bundle").evaluate(element => ({ pretext: element.dataset.pretextResult,
    width: element.clientWidth, scrollWidth: element.scrollWidth, height: element.clientHeight, scrollHeight: element.scrollHeight }));
  assert.ok(report.text.pretext);
  assert.ok(report.text.scrollWidth <= report.text.width + 1);
  assert.ok(report.text.scrollHeight <= report.text.height + 1);
  assert.deepEqual(errors, []);

  const nativePreview = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  nativePreview.on("pageerror", error => errors.push(error.message));
  await nativePreview.addInitScript(origin => localStorage.setItem("ppsDashboard.apiBase", origin), base);
  const pendingPreviews = [];
  let onPreview;
  await nativePreview.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/state") await route.fulfill({ json: previewFixture });
    else if (path === "/api/run-sequence/preview") { pendingPreviews.push(route); onPreview?.(); }
    else await route.fulfill({ status: 404, json: { detail: "No unrelated mutation in this test" } });
  });
  await nativePreview.goto(`${base}/apps/designer/frontend/compiled/index.html?desktop=1`);
  await nativePreview.waitForFunction(() => window.PPSDesignerApp?.getState()?.design);
  assert.equal(await nativePreview.evaluate(() => window.PPSDesignerApp.isHosted()), false);
  await nativePreview.locator("#edit-mode-button").click();
  for (const count of [2, 3]) {
    const requested = new Promise((done, fail) => {
      const timeout = setTimeout(() => fail(new Error("Order preview request was not sent")), 10_000);
      onPreview = () => { clearTimeout(timeout); done(); };
    });
    await nativePreview.locator("#participants").fill(String(count));
    await requested;
  }
  assert.equal(pendingPreviews.length, 2);
  const responseFor = route => {
    const payload = route.request().postDataJSON();
    return { ...previewFixture, design: payload.design,
      run_sequence_setup: { ...previewFixture.run_sequence_setup, participant_count: payload.design.protocol.participants } };
  };
  await pendingPreviews[1].fulfill({ json: responseFor(pendingPreviews[1]) });
  await nativePreview.waitForFunction(() => window.PPSDesignerApp.getState().design.protocol.participants === 3);
  const oldResponse = nativePreview.waitForResponse(response => response.url().endsWith("/api/run-sequence/preview"));
  await pendingPreviews[0].fulfill({ json: responseFor(pendingPreviews[0]) });
  await oldResponse;
  await nativePreview.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
  assert.equal(await nativePreview.evaluate(() => window.PPSDesignerApp.getState().design.protocol.participants), 3);
  assert.equal(await nativePreview.locator("#participants").inputValue(), "3");
  assert.deepEqual(errors, []);
  report.checks.push("Designer reversed HTTP preview responses preserve the latest form and state");
  const mapper = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  mapper.on("pageerror", error => errors.push(error.message));
  let failReview = true;
  await mapper.route("**/publication_study_reviews.v1-*.json", async route => {
    if (failReview) { failReview = false; await route.fulfill({ status: 503 }); }
    else await route.continue();
  });
  await mapper.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1&page=documentation#docs-publication-network`);
  const network = mapper.locator("[data-publication-network-root]");
  await network.scrollIntoViewIfNeeded();
  await mapper.locator("#publication-network-retry").waitFor({ state: "visible" });
  assert.equal(await network.getAttribute("data-publication-network-state"), "error");
  await mapper.locator("#publication-network-retry").click();
  await mapper.waitForFunction(() => document.querySelector("[data-publication-network-root]").dataset.publicationNetworkState === "ready");
  const reviewData = JSON.parse(await readFile(resolve(root, "apps/designer/frontend/publication_study_reviews.v1.json"), "utf8"));
  assert.equal(await network.getAttribute("data-publication-network-nodes"), String(reviewData.counts.publications));
  assert.equal(await network.getAttribute("data-publication-network-studies"), String(reviewData.counts.studies));
  assert.equal(await mapper.locator("#publication-network-results li").count(), 40);
  const search = mapper.locator("#publication-network-search");
  await search.fill("https://doi.org/10.1007/s00221-013-3532-2");
  assert.equal(await mapper.locator("#publication-network-results li").count(), 1);
  const result = mapper.locator(".publication-network-result-button");
  await result.focus();
  await mapper.keyboard.press("Enter");
  const detail = mapper.locator("#publication-network-detail");
  await detail.waitFor({ state: "visible" });
  assert.equal(await detail.locator("[data-study-id]").count(), 2);
  assert.match(await detail.innerText(), /Publication evidence[\s\S]*Template availability[\s\S]*Native qualification[\s\S]*Not Assessed/i);
  assert.match(await detail.innerText(), /2 reported complete · 2 derived complete · 22 contracts/);
  assert.equal(await detail.locator("[data-open-designer-template]").count(), 0);
  const study = detail.locator("[data-study-id]").first();
  await study.locator(":scope > summary").click();
  await study.locator("[data-contract-key]").first().locator(":scope > summary").click();
  const studyId = await study.getAttribute("data-study-id");
  await mapper.waitForFunction(id => new URL(location.href).searchParams.get("study") === id, studyId);
  const deepLink = mapper.url();
  await detail.screenshot({ path: resolve(output, "mapper-study-review.png") });
  await mapper.keyboard.press("Escape");
  assert.equal(await result.evaluate(element => element === document.activeElement), true);
  await search.fill("NoSuchPublication xxxxxxxxx");
  assert.equal(await mapper.locator("#publication-network-results li").count(), 0);
  assert.ok((await mapper.locator("#publication-network-status").innerText()).startsWith(`0 of ${reviewData.counts.publications}`));
  await search.fill("");
  assert.equal(await mapper.locator("#publication-network-results li").count(), 40);
  await mapper.goto(deepLink);
  await network.scrollIntoViewIfNeeded();
  await mapper.waitForFunction(id => [...document.querySelectorAll("[data-study-id]")].some(element => element.dataset.studyId === id && element.open), studyId);
  for (const width of [320, 768, 1440, 1920]) {
    await mapper.setViewportSize({ width, height: 1000 });
    await network.scrollIntoViewIfNeeded();
    await mapper.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
    assert.equal(await mapper.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, `page overflow at ${width}`);
    assert.equal(await detail.evaluate(element => element.getBoundingClientRect().right <= element.parentElement.getBoundingClientRect().right + 1), true, `detail clipping at ${width}`);
    await network.screenshot({ path: resolve(output, `mapper-${width}.png`) });
  }
  await mapper.setViewportSize({ width: 768, height: 1000 });
  await mapper.evaluate(() => {
    const sizes = [...document.querySelectorAll("[data-publication-network-root] p, [data-publication-network-root] button, [data-publication-network-root] input, [data-publication-network-root] label, [data-publication-network-root] summary, [data-publication-network-root] h3, [data-publication-network-root] h4, [data-publication-network-root] dt, [data-publication-network-root] dd, [data-publication-network-root] small")].map(element => [element, parseFloat(getComputedStyle(element).fontSize)]);
    for (const [element, size] of sizes) element.style.fontSize = `${size * 2}px`;
  });
  await network.scrollIntoViewIfNeeded();
  await network.screenshot({ path: resolve(output, "mapper-text-200.png") });
  assert.equal(await mapper.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, "page overflow at enlarged text");
  assert.equal(await detail.evaluate(element => element.getBoundingClientRect().right <= element.parentElement.getBoundingClientRect().right + 1), true, "detail clipping at enlarged text");
  report.mapperText = await mapper.locator("#publication-network-search").evaluate(element => ({ width: element.clientWidth, scrollWidth: element.scrollWidth }));
  const linkedPublication = reviewData.publications.find(publication => publication.templateIds.length);
  await mapper.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1&page=documentation&publication=${encodeURIComponent(linkedPublication.networkNodeId)}#docs-publication-network`);
  await network.scrollIntoViewIfNeeded();
  const templateLink = mapper.locator("[data-open-designer-template]").first();
  await templateLink.waitFor({ state: "visible" });
  const presetPagePromise = mapper.waitForEvent("popup");
  await templateLink.click();
  const presetPage = await presetPagePromise;
  await presetPage.waitForFunction(id => window.PPSDesignerApp?.getState()?.selected_template === id, linkedPublication.templateIds[0]);
  assert.equal(new URL(presetPage.url()).searchParams.get("template"), linkedPublication.templateIds[0]);
  assert.deepEqual(errors, []);
  report.checks.push("Mapper retry, DOI search, keyboard detail, study deep link, evidence separation, responsive layout and preset navigation");
  await writeFile(resolve(output, "report.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} catch (error) {
  for (const [index, page] of browser.contexts().flatMap(context => context.pages()).entries()) {
    await page.screenshot({ path: resolve(output, `failure-${index}.png`), fullPage: true });
  }
  throw error;
} finally {
  await browser.close();
  await new Promise(done => server.close(done));
}
