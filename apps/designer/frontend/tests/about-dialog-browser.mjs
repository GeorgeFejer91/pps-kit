import assert from "node:assert/strict";
import { resolve } from "node:path";

export async function verifyAboutDialog(page, output) {
  const evidence = [];
  const originalZoom = await page.evaluate(() => document.documentElement.style.zoom);
  for (const [width, height, theme, zoom = 1] of [[568, 320, "light"], [320, 620, "dark"], [1440, 1000, "light"], [1280, 800, "light", 2]]) {
    await page.setViewportSize({ width, height });
    await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
    await page.evaluate(zoom => { document.documentElement.style.zoom = String(zoom); }, zoom);
    const steps = width === 568 ? ["study", "stimulus", "trials", "baseline", "block", "schedule", "run"] : ["study", "trials"];
    for (const step of steps) {
      const trigger = page.locator(`[data-segment-info="${step}"]`);
      await trigger.click();
      const body = page.getByRole("region", { name: "Segment information", exact: true });
      const close = page.locator("#segment-info-modal-close");
      const help = await body.innerText();
      assert.doesNotMatch(help, /dedicated folder|researcher workspace|Runner materializes|[1-5]_(core_audio|trial_sequence|tactile_and|trial_repetition|block_csv)/);
      if (step === "study") {
        assert.match(help, /Hosted drafts stay in this browser/);
        assert.match(help, /output folder later/);
        assert.equal(await body.getByRole("link", { name: "bundled profile definitions", exact: true }).count(), 1);
      }
      if (step === "run") assert.match(help, /installed Designer requires a complete native review and explicit acceptance/);
      assert.equal(await body.evaluate(node => node.scrollTop), 0, "Each newly opened explanation starts at its beginning");
      await close.focus();
      await page.keyboard.press("Tab");
      assert.equal(await body.evaluate(node => node === document.activeElement), true);
      const before = await close.boundingBox();
      const geometry = await body.evaluate(node => ({
        dialog: node.closest('[role="dialog"]').getBoundingClientRect().toJSON(),
        height: node.clientHeight, scrollHeight: node.scrollHeight,
        width: node.clientWidth, scrollWidth: node.scrollWidth,
      }));
      assert.ok(geometry.dialog.top >= 0 && geometry.dialog.bottom <= height && geometry.dialog.left >= 0 && geometry.dialog.right <= width);
      assert.equal(geometry.width, geometry.scrollWidth);
      if (geometry.scrollHeight > geometry.height + 1) {
        await page.keyboard.press("End");
        await page.waitForFunction(() => {
          const node = document.querySelector(".segment-info-body");
          return Math.abs(node.scrollHeight - node.clientHeight - node.scrollTop) <= 2;
        });
      }
      const after = await close.boundingBox();
      assert.equal(after.y, before.y, "Heading and close anchor remain visible while the document is read");
      await page.screenshot({ path: resolve(output, `about-${step}-${width}-${height}-${theme}-zoom${zoom}.png`) });
      await page.keyboard.press("Escape");
      assert.equal(await trigger.evaluate(node => node === document.activeElement), true);
      evidence.push({ step, width, height, theme, zoom, help, ...geometry, headingAnchored: true, keyboardReachedEnd: true, focusReturned: true });
    }
  }
  await page.evaluate(zoom => { document.documentElement.style.zoom = zoom; }, originalZoom);
  return evidence;
}
