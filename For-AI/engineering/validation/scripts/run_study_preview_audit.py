"""Check the standalone study preview against the assembled Pages site."""

import argparse
from functools import partial
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[4]
PAGES = ROOT / "dist" / "pages"
ARTIFACTS = ROOT / "artifacts" / "browser-runner-launch"


class QuietHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("X-PPS-Audit-Revision", self.server.audit_revision)
        super().end_headers()

    def log_message(self, *args):
        pass

    def copyfile(self, source, outputfile):
        try:
            super().copyfile(source, outputfile)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # A browser can cancel background precache requests when its test context closes.
            pass


def play(page, app, origin, *, offline=False):
    button = app.get_by_role("button", name="Play or stop Pink frontal", exact=True)
    expect(button).to_be_visible()
    with page.expect_response(lambda response: response.url.endswith("looming_Pink_frontal.wav")) as played:
        button.press("Enter")
    assert played.value.ok and played.value.url.startswith(f"{origin}/")
    if offline:
        assert played.value.from_service_worker
    expect(app.locator("#toast")).to_contain_text("Soundcheck: Pink frontal")
    expect(button).to_have_class(re.compile(r"\bplaying\b"))
    expect(button).to_be_focused()
    button.press("Enter")
    expect(button).not_to_have_class(re.compile(r"\bplaying\b"))


def audit(browser, origin, server):
    with browser.new_context(viewport={"width": 1440, "height": 900}) as context:
        context.add_init_script(
            "localStorage.setItem('ppsDashboard.apiBase', 'http://127.0.0.1:18766')"
        )
        page = context.new_page()
        requests = []
        page.on("request", lambda request: requests.append(request.url))
        page.goto(f"{origin}/", wait_until="domcontentloaded")
        app = page.frame_locator("iframe")
        study = app.locator("#profile-inspection-id")
        expect(study).to_have_text("study5_box_breathing_pps")
        expect(app.get_by_label("Backend URL")).to_be_hidden()
        expect(app.get_by_label("Mutation token")).to_be_hidden()
        play(page, app, origin)
        assert not any(urlsplit(url).path.startswith("/api/") for url in requests), requests

        cdp = context.new_cdp_session(page)
        page.wait_for_function("navigator.serviceWorker.controller !== null")
        assert not cdp.send("Page.getInstallabilityErrors")["installabilityErrors"]
        server.audit_revision = "online-revisit"
        with page.expect_response(
            lambda response: response.request.is_navigation_request()
            and urlsplit(response.url).path == "/app/index.html"
        ) as refreshed:
            shell = page.reload(wait_until="domcontentloaded")
        assert shell and shell.headers.get("x-pps-audit-revision") == "online-revisit", (
            "An online return visit reused the cached site shell."
        )
        assert refreshed.value.headers.get("x-pps-audit-revision") == "online-revisit", (
            "An online return visit reused the cached Planner document."
        )
        expect(study).to_have_text("study5_box_breathing_pps")
        context.set_offline(True)
        page.set_viewport_size({"width": 320, "height": 800})
        page.reload(wait_until="domcontentloaded")
        expect(study).to_have_text("study5_box_breathing_pps")
        play(page, app, origin, offline=True)


def audit_routes(browser, origin):
    with browser.new_context(viewport={"width": 1440, "height": 900}) as context:
        page = context.new_page()
        page.goto(f"{origin}/download/")
        app = page.frame_locator("iframe")
        nav = app.get_by_role("navigation", name="PPS Kit", exact=True)
        names = ("Experiment Planner", "Experiment Runner", "Documentation", "Downloads")
        links = nav.get_by_role("link")
        expect(links).to_have_count(len(names))
        for index, name in enumerate(names):
            expect(links.nth(index)).to_have_accessible_name(name)
        expect(nav.get_by_role("link", name="Downloads")).to_have_attribute("aria-current", "page")
        expect(app.locator(".windows-installers h3")).to_have_count(3)
        expect(app.get_by_role("link", name="View releases")).to_have_count(1)
        expect(app.get_by_role("heading", name="Browser app (PWA)")).to_be_visible()
        expect(app.get_by_role("link", name="Open web app")).to_have_attribute("target", "_top")
        page.screenshot(path=ARTIFACTS / "downloads-desktop.png")

        page.set_viewport_size({"width": 320, "height": 800})
        frame = page.frames[1]
        frame.add_style_tag(content="""
          .hosted-page-nav a, .download-card p, .download-card h3 {
            font-size: 200% !important; line-height: 1.5 !important;
            letter-spacing: .12em !important; word-spacing: .16em !important;
          }
        """)
        assert frame.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert app.locator("#downloads-page").evaluate(
            "(node) => [...node.querySelectorAll('article, a')].every(el => el.scrollWidth <= el.clientWidth)"
        )
        page.screenshot(path=ARTIFACTS / "downloads-320-text-spacing.png")
        runner = nav.get_by_role("link", name="Experiment Runner")
        expect(runner.locator("[data-pretext]:visible")).to_have_attribute(
            "data-pretext-result", re.compile("fit|reflow|dom-fallback")
        )
        runner.press("Enter")
        page.wait_for_url(f"{origin}/experiment-runner/")
        assert len(page.frames) == 1
        expect(page.get_by_role("link", name="Experiment Runner")).to_have_attribute("aria-current", "page")
        expect(page.get_by_role("button", name="Send beacon")).to_be_enabled()
        expect(page.get_by_role("button", name="Scan beacon")).to_be_hidden()
        page.screenshot(path=ARTIFACTS / "runner-320.png")
        page.get_by_role("button", name="Control another device").press("Enter")
        expect(page.get_by_role("button", name="Scan beacon")).to_be_enabled()
        expect(page.get_by_role("button", name="Send beacon")).to_be_hidden()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.get_by_role("button", name="Run on this device").click()

        page.get_by_role("button", name="Submit setup").click()
        page.get_by_role("button", name="Prepare demo").click()
        expect(page.get_by_role("button", name="Start locally")).to_be_disabled()
        page.get_by_role("button", name="Arm outputs locally").click()
        page.get_by_role("button", name="Start locally").click()
        expect(page.get_by_role("button", name="Tap response")).to_be_enabled()
        page.get_by_role("button", name="Tap response").click()
        expect(page.locator("#phone-run-state")).to_have_text("Completed", timeout=6000)
        expect(page.get_by_role("button", name="Download event log")).to_be_enabled()

        page.get_by_role("link", name="Experiment Planner").click()
        page.wait_for_url(f"{origin}/")
        expect(page.frame_locator("iframe").get_by_role("link", name="Experiment Planner")).to_have_attribute(
            "aria-current", "page"
        )


def audit_live_beacon(browser, origin):
    # Two independent browser contexts. Only the physical vibration API is instrumented.
    with browser.new_context(viewport={"width": 390, "height": 844}) as target_context, browser.new_context() as controller_context:
        target_context.add_init_script("""
          window.ppsVibrationCalls = [];
          Object.defineProperty(navigator, 'vibrate', { value: (value) => (ppsVibrationCalls.push(value), true) });
        """)
        target = target_context.new_page()
        controller = controller_context.new_page()
        target.goto(f"{origin}/experiment-runner/")
        controller.goto(f"{origin}/experiment-runner/")
        target.get_by_role("button", name="Send beacon").click()
        expect(target.locator("#target-beacon-status")).to_have_text("Advertising", timeout=25000)
        controller.get_by_role("button", name="Control another device").click()
        controller.get_by_role("button", name="Scan beacon").click()
        expect(controller.locator("#beacon-status")).to_have_text("Browsing", timeout=25000)
        candidate = controller.locator("#beacon-targets button")
        expect(target.locator("#target-beacon-code")).to_be_visible()
        beacon_code = target.locator("#target-beacon-code").inner_text().split()[-1]
        candidate.filter(has_text=beacon_code).click(timeout=25000)
        controller.get_by_role("button", name="Request private session").click(timeout=25000)
        expect(controller.get_by_role("button", name="Connect", exact=True)).to_be_disabled()
        expect(target.get_by_role("button", name="Allow to pair")).to_be_visible(timeout=15000)
        target.get_by_role("button", name="Allow to pair").click()
        controller.get_by_role("button", name="Connect", exact=True).click(timeout=25000)
        expect(controller.locator("#companion-status")).to_have_text("Controls ready", timeout=25000)
        expect(target.locator("#target-qr")).to_be_hidden()
        expect(controller.get_by_role("button", name="Start part")).to_be_disabled()
        target.get_by_role("button", name="Submit setup").click()
        controller.get_by_role("button", name="Prepare demo").click()
        expect(controller.get_by_role("button", name="Start part")).to_be_disabled()
        target.get_by_role("button", name="Arm outputs locally").click()
        expect(controller.get_by_role("button", name="Start part")).to_be_enabled(timeout=12000)
        controller.get_by_role("button", name="Start part").click()
        expect(target.locator("#phone-run-state")).to_have_text("Running", timeout=12000)
        expect(target.locator("#phone-run-state")).to_have_text("Completed", timeout=6000)
        assert target.evaluate("ppsVibrationCalls.some(Array.isArray)"), "No scheduled tactile output call"
        target.get_by_role("button", name="Disconnect controller").click()
        expect(controller.get_by_role("button", name="Start part")).to_be_hidden(timeout=15000)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-beacon", action="store_true", help="also use the live VDO.Ninja service")
    parser.add_argument("--runner-only", action="store_true", help="skip the install and cached study audit")
    args = parser.parse_args()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if not (PAGES / "index.html").is_file():
        raise SystemExit("Assemble the Pages site with build_pages.mjs before running this audit.")
    handler = partial(QuietHandler, directory=PAGES)
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        server.audit_revision = "initial"
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    origin = f"http://127.0.0.1:{server.server_port}"
                    if not args.runner_only:
                        audit(browser, origin, server)
                    audit_routes(browser, origin)
                    print("Downloads, top-level Runner navigation, and the local browser demo passed.")
                    if args.live_beacon:
                        audit_live_beacon(browser, origin)
                        print("Live two-browser beacon pairing and remote start passed.")
                finally:
                    browser.close()
        finally:
            server.shutdown()
            thread.join()
    if not args.runner_only:
        print("Online refresh, keyboard playback, Chromium installability and offline Study 5 passed.")


if __name__ == "__main__":
    main()
