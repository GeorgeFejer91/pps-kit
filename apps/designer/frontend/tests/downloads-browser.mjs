import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { join } from "node:path";

export async function verifyNativeDownloads(page, output) {
  const release = "https://github.com/GeorgeFejer91/pps-kit/releases";
  const tag = "native-preview-v0.1.0";
  const links = {
    "download-designer": `${release}/download/${tag}/PPS%20Experiment%20Designer%20Preview_0.1.0_x64-setup.exe`,
    "download-runner": `${release}/download/${tag}/PPS%20Experiment%20Runner%20Preview_0.1.0_x64-setup.exe`,
    "download-software": `${release}/tag/${tag}`,
    "download-checksums": `${release}/download/${tag}/SHA256SUMS`,
  };
  await page.getByRole("tab", { name: "Downloads", exact: true }).press("Enter");
  await page.locator("#downloads-page").waitFor({ state: "visible" });
  await page.waitForFunction(() => !document.getElementById("toast").classList.contains("visible"));
  assert.match(await page.locator("#downloads-page").innerText(), /V1 Python\/Qt bootstrappers and a combined Toolkit installer are not available/);
  for (const [id, url] of Object.entries(links)) {
    assert.equal(await page.locator(`#${id}`).getAttribute("href"), url);
    assert.equal(await page.locator(`#${id}`).getAttribute("target"), "_blank");
    assert.equal(await page.locator(`#${id}`).getAttribute("rel"), "noopener noreferrer");
  }
  await page.locator("#download-designer").focus();
  await page.keyboard.press("Tab");
  assert.equal(await page.evaluate(() => document.activeElement.id), "download-runner");
  await page.keyboard.press("Tab");
  assert.equal(await page.evaluate(() => document.activeElement.id), "download-software");
  // Verify keyboard navigation to the exact planned tag, without claiming release availability.
  const route = target => target.fulfill({ contentType: "text/html", body: "Planned preview release target" });
  await page.context().route(links["download-software"], route);
  const popupEvent = page.waitForEvent("popup");
  await page.keyboard.press("Enter");
  const popup = await popupEvent;
  await popup.waitForLoadState("domcontentloaded");
  assert.equal(popup.url(), links["download-software"]);
  await popup.close();
  await page.context().unroute(links["download-software"], route);

  const geometry = [];
  for (const [width, zoom] of [[390, 1], [900, 1], [1440, 1], [1440, 2]]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(value => { document.documentElement.style.zoom = String(value); }, zoom);
    await page.waitForFunction(ids => ids.every(id => document.getElementById(id).dataset.pretextResult), Object.keys(links));
    for (const id of Object.keys(links)) {
      const link = page.locator(`#${id}`);
      await link.scrollIntoViewIfNeeded();
      const item = await link.evaluate(node => ({ id: node.id, result: node.dataset.pretextResult,
        fontSize: getComputedStyle(node).fontSize, overflow: node.scrollWidth > node.clientWidth + 1,
        outsideViewport: node.getBoundingClientRect().left < -1 || node.getBoundingClientRect().right > innerWidth + 1 }));
      assert.ok(["fit", "reflow", "dom-fallback"].includes(item.result), `${id}: ${item.result}`);
      assert.equal(item.overflow, false, `${id} overflow at ${width}px / ${zoom}`);
      assert.equal(item.outsideViewport, false, `${id} outside viewport at ${width}px / ${zoom}`);
      geometry.push({ width, zoom, ...item });
    }
    await page.locator("#downloads-installer-title").scrollIntoViewIfNeeded();
    if (zoom === 1 && [390, 1440].includes(width)) await page.screenshot({ path: join(output, `downloads-${width}.png`) });
  }
  await writeFile(join(output, "downloads-report.json"), JSON.stringify({ links, geometry, keyboardOrder: true,
    exactReleaseTarget: true, remoteAvailabilityAssessed: false }, null, 2));
  await page.evaluate(() => { document.documentElement.style.zoom = ""; });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("tab", { name: "Documentation", exact: true }).click();
  const section = page.locator("#docs-emulatable-studies");
  assert.equal(await section.getByRole("heading", { level: 2 }).innerText(), "Archived Study Configurations");
  assert.doesNotMatch(await section.innerText(), /six study profiles|five publications|Studies Currently Emulatable/i);
  assert.match(await section.innerText(), /Template availability and native software checks are separate from scientific equivalence/);
  const mapLink = section.getByRole("link", { name: "Open Audiotactile Map", exact: true });
  const configurationGeometry = [];
  for (const [width, zoom] of [[320, 1], [900, 1], [1440, 1], [1440, 2]]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(value => { document.documentElement.style.zoom = String(value); }, zoom);
    await mapLink.scrollIntoViewIfNeeded();
    await page.waitForFunction(() => document.querySelector('#docs-emulatable-studies [data-pretext]').dataset.pretextResult);
    const rendered = await section.evaluate(node => [...node.querySelectorAll('h2,.info-copy,.button-link')].map(element => ({
      text: element.textContent, overflow: element.scrollWidth > element.clientWidth + 1,
      outsideViewport: element.getBoundingClientRect().left < -1 || element.getBoundingClientRect().right > innerWidth + 1,
    })));
    assert.ok(rendered.every(item => !item.overflow && !item.outsideViewport), `${width}px / ${zoom}: configuration copy reflows`);
    configurationGeometry.push({ width, zoom, rendered });
  }
  await page.evaluate(() => { document.documentElement.style.zoom = ""; });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await section.screenshot({ path: join(output, "archived-configurations.png") });
  await mapLink.focus(); await page.keyboard.press("Enter");
  await page.waitForFunction(() => location.hash === "#docs-publication-network");
  await page.waitForFunction(() => document.getElementById("publication-network-inventory-note").textContent.includes("inventory and contract audits complete"));
  assert.equal(await page.locator("#documentation-page").isVisible(), true);
  await writeFile(join(output, "archived-configurations-report.json"), JSON.stringify({ configurationGeometry,
    keyboardMapRoute: true, generatedAuditText: await page.locator("#publication-network-inventory-note").innerText() }, null, 2));
  await page.getByRole("tab", { name: "Experiment Designer", exact: true }).click();
}
