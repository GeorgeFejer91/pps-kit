"""Check the standalone study preview against the assembled Pages site."""

from functools import partial
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[4]
PAGES = ROOT / "dist" / "pages"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def play(page, panel, label, filename, origin, *, offline=False):
    button = panel.get_by_role("button", name=f"Play {label}", exact=True)
    expect(button).to_be_visible()
    with page.expect_response(lambda response: response.url.endswith(filename)) as played:
        button.press("Enter")
    assert played.value.ok and played.value.url.startswith(f"{origin}/")
    if offline:
        assert played.value.from_service_worker
    expect(button).to_have_attribute("aria-pressed", "true")
    expect(button).to_be_focused()
    button.press("Enter")
    expect(button).to_have_attribute("aria-pressed", "false")


def audit(browser, origin):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(
        "localStorage.setItem('ppsDashboard.apiBase', 'http://127.0.0.1:18766')"
    )
    context.route("http://127.0.0.1:18766/**", lambda route: route.abort())
    page = context.new_page()
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    page.goto(f"{origin}/", wait_until="domcontentloaded")
    app = page.frame_locator("iframe")
    study = app.locator("#profile-inspection-id")
    expect(study).to_have_text("study5_box_breathing_pps")
    expect(app.get_by_label("Backend URL")).to_be_hidden()
    expect(app.get_by_label("Mutation token")).to_be_hidden()
    expect(app.get_by_role("link", name="Desktop suite")).to_have_attribute("href", "../download/")
    panel = app.locator("#study-preview")
    play(page, panel, "Pink frontal", "looming_Pink_frontal.wav", origin)

    app.get_by_role("combobox", name="Profile", exact=True).press("Enter")
    app.get_by_role("option", name=re.compile(r"Canzoneri.*2012", re.I)).click()
    expect(study).to_have_text("canzoneri_2012_dynamic_sounds")
    expect(app.locator("#filmstrip-list .filmstrip-row").first).to_be_attached()
    play(page, panel, "Pink moving sound", "looming_Pink_moving_sound.wav", origin)
    assert not any(urlsplit(url).path.startswith("/api/") for url in requests), requests

    cdp = context.new_cdp_session(page)
    page.wait_for_function("navigator.serviceWorker.controller !== null")
    assert not cdp.send("Page.getInstallabilityErrors")["installabilityErrors"]
    context.set_offline(True)
    page.set_viewport_size({"width": 320, "height": 800})
    page.reload(wait_until="domcontentloaded")
    expect(study).to_have_text("study5_box_breathing_pps")
    play(page, panel, "Pink frontal", "looming_Pink_frontal.wav", origin, offline=True)

    app.get_by_role("button", name="Use dark theme").click()
    expect(panel.locator("button").first).to_have_attribute("data-pretext-result", re.compile("fit|reflow"))
    assert panel.evaluate("(el) => el.scrollWidth <= el.clientWidth")
    frame = page.frames[1]
    frame.add_style_tag(content="""
      #study-preview p, #study-preview button {
        font-size: 200% !important; line-height: 1.5 !important;
        letter-spacing: .12em !important; word-spacing: .16em !important;
      }
    """)
    assert panel.evaluate("""(el) => [el, ...el.querySelectorAll('button')].every(
      (node) => node.scrollWidth <= node.clientWidth && node.scrollHeight <= node.clientHeight
    )""")
    context.set_offline(False)


def main():
    if not (PAGES / "index.html").is_file():
        raise SystemExit("Assemble the Pages site with build_pages.mjs before running this audit.")
    handler = partial(QuietHandler, directory=PAGES)
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    audit(browser, f"http://127.0.0.1:{server.server_port}")
                finally:
                    browser.close()
        finally:
            server.shutdown()
            thread.join()
    print("Study selection, keyboard playback, Chromium installability and offline Study 5 passed.")


if __name__ == "__main__":
    main()
