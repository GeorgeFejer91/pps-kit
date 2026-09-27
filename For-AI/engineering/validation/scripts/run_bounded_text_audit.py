"""Rendered check of the shared Pretext contract and both compiled HTML apps."""
from __future__ import annotations

import argparse
import json
import threading
from contextlib import contextmanager
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright
from run_designer_visual_layout_audit import QuietHandler, REPO_ROOT


@contextmanager
def serve_repository():
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(REPO_ROOT)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/bounded-text-audit"))
    output = parser.parse_args().output_dir
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with serve_repository() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(base)
        page.set_content('''<html lang="en"><style>
          * { box-sizing: border-box; } body { margin: 12px; }
          button { font: 16px/24px sans-serif; width: 100%; padding: 8px;
            white-space: normal; overflow-wrap: break-word;
            min-height: max(44px, var(--pretext-min-height, 0px)); }
          [data-pretext-result="no-fit"] { overflow-wrap: anywhere; }
          </style><button data-pretext id="label">Export experiment JSON</button></html>''')
        page.add_script_tag(type="module", content=f'''
          import * as pretext from "{base}/apps/designer/frontend/node_modules/@chenglou/pretext/dist/layout.js";
          import {{ initializeBoundedText }} from "{base}/packages/pps-resources/assets/ui/bounded-text.mjs";
          window.textLayout = initializeBoundedText(document.body, pretext);
        ''')
        page.wait_for_function("document.querySelector('#label').dataset.pretextResult === 'fit'")
        for label, size, spacing in [
            ("Export experiment JSON", 16, False),
            ("Experimentprofil mit vollständig überprüften Audiodateien exportieren", 32, False),
            ("音声ファイルと実験計画を確認して書き出す", 32, False),
            ("experiment_" + "long_identifier_" * 10, 32, False),
            ("Export verified experimental profile and local audio ingredients", 32, True),
        ]:
            page.evaluate("""({label,size,spacing}) => {
              const button = document.querySelector('#label'); button.textContent = label;
              button.style.fontSize = `${size}px`; button.style.lineHeight = `${size * 1.5}px`;
              button.style.letterSpacing = spacing ? '0.12em' : 'normal';
              button.style.wordSpacing = spacing ? '0.16em' : 'normal';
              window.textLayout.refresh();
            }""", {"label": label, "size": size, "spacing": spacing})
            page.wait_for_timeout(120)
            state = page.evaluate("""() => {
              const node = document.querySelector('#label');
              return {result:node.dataset.pretextResult,size:parseFloat(getComputedStyle(node).fontSize),
                lines:Number(node.dataset.pretextLineCount), width:node.clientWidth, scroll:node.scrollWidth,
                height:node.clientHeight,scrollHeight:node.scrollHeight,page:document.documentElement.scrollWidth};
            }""")
            assert state["size"] == size, state
            assert state["scroll"] <= state["width"] + 1 and state["scrollHeight"] <= state["height"] + 1, state
            assert state["page"] <= 320, state
            assert state["result"] not in {None, "unavailable"}, state
            if spacing:
                assert state["result"] == "dom-fallback", state
            results.append(state)
        page.screenshot(path=str(output / "enlarged-localized-label.png"))
        for app, path, selector in [
            ("designer", "apps/designer/frontend/compiled/index.html?page=toolkit", "#run-segment"),
            ("phone", "apps/runner/compiled/companion/index.html", "main"),
        ]:
            for width in (320, 390, 1440, 1920):
                page.set_viewport_size({"width": width, "height": 900})
                page.goto(f"{base}/{path}", wait_until="networkidle")
                page.wait_for_function("document.querySelector('[data-pretext-result]') !== null")
                state = page.evaluate("""(selector) => ({
                  width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,
                  measured:document.querySelectorAll(`${selector} [data-pretext-result]`).length
                })""", selector)
                assert state["measured"] > 0 and state["scroll"] <= state["width"] + 1, (app, width, state)
                if app == "designer":
                    page.locator(selector).scroll_into_view_if_needed()
                page.screenshot(path=str(output / f"{app}-{width}.png"))
                results.append({"app": app, **state})
        page.set_viewport_size({"width": 320, "height": 900})
        page.goto(f"{base}/apps/runner/compiled/companion/index.html", wait_until="networkidle")
        page.locator('[data-mode="target"]').click()
        page.locator("#create-phone-target").click()
        page.locator("#phone-prepare").click()
        page.locator("#phone-setup").click()
        page.locator("#phone-audio-enabled").uncheck()
        page.locator("#phone-vibration-enabled").uncheck()
        page.locator("#arm-phone").click()
        page.locator("#phone-start").click()
        page.wait_for_function("document.querySelector('#phone-run-state').textContent === 'Running'")
        page.evaluate('''() => {
          Object.defineProperty(document, 'visibilityState', {configurable:true, get:()=>'hidden'});
          document.dispatchEvent(new Event('visibilitychange'));
          document.dispatchEvent(new Event('freeze'));
          window.dispatchEvent(new Event('pagehide'));
        }''')
        page.wait_for_function("document.querySelector('#phone-start').disabled && document.querySelector('#disarm-phone').disabled")
        page.evaluate('''() => {
          Object.defineProperty(document, 'visibilityState', {configurable:true, get:()=>'visible'});
          window.dispatchEvent(new Event('pageshow'));
          document.dispatchEvent(new Event('resume'));
        }''')
        assert page.locator("#phone-run-state").inner_text() == "Interrupted"
        assert page.locator("#phone-start").is_disabled()
        assert page.locator("#disarm-phone").is_disabled()
        page.locator("#phone-run-state").scroll_into_view_if_needed()
        page.screenshot(path=str(output / "phone-suspended-output.png"))
        results.append({"app": "phone", "suspension": "outputs_disarmed_no_replay", "physical_qualification": False})
        page.evaluate('''() => {
          document.documentElement.style.fontSize = '32px';
          for (const node of document.querySelectorAll('*')) {
            node.style.letterSpacing = '0.12em'; node.style.wordSpacing = '0.16em';
          }
        }''')
        page.wait_for_timeout(150)
        page.locator("#phone-run-state").scroll_into_view_if_needed()
        enlarged = page.evaluate('''() => ({width:document.documentElement.clientWidth,
          scroll:document.documentElement.scrollWidth})''')
        if enlarged["scroll"] > enlarged["width"] + 1:
            enlarged["overflow"] = page.evaluate('''() => [...document.querySelectorAll('body *')]
              .filter(node=>node.getBoundingClientRect().right>321 || node.scrollWidth>node.clientWidth+1)
              .map(node=>({tag:node.tagName,id:node.id,cls:node.className,
                right:node.getBoundingClientRect().right, width:node.clientWidth, scroll:node.scrollWidth,
                text:node.textContent.slice(0,70)})).slice(0,16)''')
            page.screenshot(path=str(output / "phone-target-enlarged-failure.png"))
        assert enlarged["scroll"] <= enlarged["width"] + 1, enlarged
        page.screenshot(path=str(output / "phone-target-enlarged-spacing.png"))
        results.append({"app": "phone", "enlarged_text_and_spacing": True, **enlarged})
        browser.close()
    (output / "report.json").write_text(json.dumps({"passed": True, "cases": results}, indent=2), encoding="utf-8")
    print(f"Passed {len(results)} rendered cases; screenshots: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
