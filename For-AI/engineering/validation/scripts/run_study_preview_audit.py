"""Check the standalone study preview against the assembled Pages site."""

import argparse
from functools import partial
import json
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
        expect(app.locator("#designer-capability-badge")).to_have_text("browser preview")
        expect(app.locator("#designer-capability-badge")).to_be_visible()
        expect(app.locator(".rail #designer-theme-toggle")).to_be_visible()
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


def audit_shared_shell(browser, origin):
    routes = (
        ("", "Experiment Planner"),
        ("experiment-runner/", "Experiment Runner"),
        ("documentation/", "Documentation"),
        ("download/", "Downloads"),
        ("", "Experiment Planner"),
    )
    for width in (320, 1440, 1920):
        with browser.new_context(viewport={"width": width, "height": 900}, color_scheme="dark") as context:
            page = context.new_page()
            page.goto(f"{origin}/")
            reference = None
            for index, (path, name) in enumerate(routes):
                page.wait_for_url(f"{origin}/{path}")
                app = page if path == "experiment-runner/" else page.frame_locator("iframe.dashboard-frame")
                nav = app.get_by_role("navigation", name="PPS Kit", exact=True)
                current = nav.get_by_role("link", name=name, exact=True)
                expect(current).to_have_attribute("aria-current", "page")
                expect(current.locator("[data-pretext]:visible")).to_have_attribute(
                    "data-pretext-result", re.compile("fit|reflow|dom-fallback")
                )
                theme_parent = nav if width <= 760 else app.locator(".rail")
                expect(theme_parent.get_by_role("button", name="Dark theme")).to_have_attribute(
                    "aria-pressed", "true"
                )

                tabs = nav.get_by_role("link").all()
                chrome = [*tabs, nav, app.locator(".header-credits"), app.locator(".rail")]
                if width > 760:
                    chrome.append(app.locator(".site-tabs"))
                bounds = [element.bounding_box() for element in chrome]
                assert all(bounds), (width, path, bounds)
                if reference is None:
                    reference = bounds
                else:
                    for expected, actual in zip(reference, bounds):
                        assert all(abs(expected[key] - actual[key]) <= 1 for key in expected), (
                            width, path, expected, actual
                        )
                if path == "experiment-runner/":
                    assert len(page.frames) == 1
                    expect(app.locator(".rail").get_by_role("group", name="Runner mode")).to_be_visible()
                    for image in app.locator(".header-credits img").all():
                        assert image.evaluate("node => node.complete && node.naturalWidth > 0")
                    page.screenshot(path=ARTIFACTS / f"runner-shell-{width}-dark.png")
                if index + 1 < len(routes):
                    nav.get_by_role("link", name=routes[index + 1][1], exact=True).press("Enter")


def open_runner_dialog(page, dialog_id):
    launcher = page.locator(f'[data-dialog="{dialog_id}"]')
    launcher.click()
    expect(page.locator(f"#{dialog_id}")).to_be_visible()
    return launcher


def close_runner_dialog(page, dialog_id):
    page.locator(f"#{dialog_id} [data-close-dialog]").click()
    expect(page.locator(f"#{dialog_id}")).to_be_hidden()


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
        for position, (title, icon) in enumerate([
            ("Experiment Planner", "pps_toolkit_icon"),
            ("Experiment Runner", "pps_runner_icon"),
            ("Experiment Planner + Runner Suite", "pps_suite_icon"),
        ]):
            heading = app.locator(".installer-card-heading").nth(position)
            expect(heading.get_by_role("heading")).to_have_text(title)
            image = heading.locator("img")
            expect(image).to_have_attribute("src", re.compile(fr"{icon}-[\w-]+\.svg$"))
            expect(image).to_have_attribute("alt", "")
            expect(image).to_be_visible()
            expect(image).to_have_js_property("naturalWidth", 512)
            expect(heading.locator("h3")).to_have_attribute(
                "data-pretext-result", re.compile("fit|reflow|dom-fallback")
            )
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
        app.locator(".windows-installers").screenshot(path=ARTIFACTS / "installer-icons-320-text-spacing.png")
        runner = nav.get_by_role("link", name="Experiment Runner")
        expect(runner.locator("[data-pretext]:visible")).to_have_attribute(
            "data-pretext-result", re.compile("fit|reflow|dom-fallback")
        )
        nav.get_by_role("link", name="Experiment Planner", exact=True).click()
        page.wait_for_url(f"{origin}/")
        expect(app.locator("#designer-capability-badge")).to_be_hidden()
        expect(runner.locator(".tab-label-short")).to_have_text("Runner")
        expect(runner.locator(".tab-label-short")).to_be_visible()
        theme = nav.locator("#designer-theme-toggle")
        expect(theme).to_be_visible()
        pressed = theme.get_attribute("aria-pressed")
        theme.press("Enter")
        expect(theme).to_have_attribute("aria-pressed", "false" if pressed == "true" else "true")
        runner.press("Enter")
        page.wait_for_url(f"{origin}/experiment-runner/")
        assert len(page.frames) == 1
        expect(page.get_by_role("link", name="Experiment Runner")).to_have_attribute("aria-current", "page")
        launcher = open_runner_dialog(page, "remote-center")
        expect(page.locator("#remote-center-title")).to_be_focused()
        expect(page.locator("#target-beacon-start")).to_be_enabled()
        expect(page.locator("#beacon-browse")).to_be_hidden()
        expect(page.locator('#remote-center [data-mode="target"] .icon-label')).to_have_attribute(
            "data-pretext-result", re.compile("fit|reflow|dom-fallback")
        )
        page.screenshot(path=ARTIFACTS / "runner-remote-320.png")
        page.get_by_role("button", name="Scan for a beacon").press("Enter")
        expect(page.locator("#beacon-browse")).to_be_enabled()
        expect(page.locator("#target-beacon-start")).to_be_hidden()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.keyboard.press("Escape")
        expect(launcher).to_be_focused()
        page.get_by_role("button", name="Run on this device").click()
        page.screenshot(path=ARTIFACTS / "runner-320.png")

        open_runner_dialog(page, "phone-study-settings")
        page.get_by_role("button", name="Submit setup").click()
        page.get_by_role("button", name="Prepare demo").click()
        close_runner_dialog(page, "phone-study-settings")
        expect(page.get_by_role("button", name="Start locally")).to_be_disabled()
        open_runner_dialog(page, "phone-output-settings")
        page.get_by_role("button", name="Arm outputs locally").click()
        close_runner_dialog(page, "phone-output-settings")
        page.get_by_role("button", name="Start locally").click()
        expect(page.locator("#phone-response")).to_be_visible()
        expect(page.get_by_role("button", name="Stop experiment")).to_be_focused()
        assert page.locator(".app-shell").evaluate("(shell) => shell.inert")
        expect(page.locator("#phone-run-state")).to_have_text("Completed", timeout=6000)
        expect(page.get_by_role("button", name="Download event log")).to_be_enabled()

        page.get_by_role("link", name="Experiment Planner").click()
        page.wait_for_url(f"{origin}/")
        expect(page.frame_locator("iframe").get_by_role("link", name="Experiment Planner")).to_have_attribute(
            "aria-current", "page"
        )


def stage_completion_fixture(context):
    """Serve a two-block test plan without modifying the assembled site."""
    root = PAGES / "assets" / "phone-studies"
    # Its first trial ends before the final response window closes.
    reference = root / "serino_2015_peri_trunk_exp1"
    plan = json.loads((reference / "study.json").read_text(encoding="utf-8"))
    block = plan["parts"][0]["blocks"][0]
    block["trials"] = block["trials"][:1]
    block["length_samples"] = block["trials"][0]["end_sample"]
    clip = plan["clips"][block["trials"][0]["clip"]]
    plan["clips"] = {block["trials"][0]["clip"]: clip}
    plan["profile_id"] = "phone_timing_fixture"
    plan["title"] = "Phone timing validation fixture"
    first_trial = block["trials"][0]
    next_trial = {**first_trial, "number": 2}
    for field, sample in first_trial.items():
        if field.endswith("_sample") and sample is not None:
            next_trial[field] = sample + block["length_samples"]
    second_block = {**block, "label": "Second block", "length_samples": next_trial["end_sample"],
                    "trials": [first_trial, next_trial]}
    plan["parts"] = [{
        "number": 1,
        "instructions": [{
            "slot": "after_each_block", "label": "Continue to next stage", "continue_mode": "click",
            "delay_s": 0, "button_label": "Continue", "clip": None,
        }],
        "blocks": [block, second_block],
    }]
    context.route("**/phone-studies/index.json", lambda route: route.fulfill(json=[
        {"id": plan["profile_id"], "title": plan["title"]},
    ]))
    context.route("**/phone-studies/phone_timing_fixture/study.json", lambda route: route.fulfill(json=plan))
    context.route("**/phone-studies/phone_timing_fixture/" + clip["file"],
                  lambda route: route.fulfill(path=reference / clip["file"]))
    return plan["profile_id"]


def audit_local_phone_study(browser, origin):
    with browser.new_context(viewport={"width": 320, "height": 700}, has_touch=True, is_mobile=True) as context:
        context.add_init_script("""
          window.ppsVibrationCalls = [];
          window.ppsRejectVibration = true;
          Object.defineProperty(navigator, 'vibrate', { value: (value) => {
            ppsVibrationCalls.push(value);
            return !ppsRejectVibration;
          }});
        """)
        study = stage_completion_fixture(context)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{origin}/experiment-runner/")
        open_runner_dialog(page, "phone-study-settings")
        page.locator("#phone-study").select_option(study)
        page.get_by_role("button", name="Prepare study", exact=True).click()
        page.get_by_role("button", name="Submit setup").click()
        close_runner_dialog(page, "phone-study-settings")
        open_runner_dialog(page, "phone-output-settings")
        page.get_by_role("button", name="Arm outputs locally").click()
        expect(page.locator("#companion-toast")).to_contain_text("refused a vibration request")
        expect(page.get_by_role("button", name="Start locally")).to_be_disabled()
        page.evaluate("ppsRejectVibration = false")
        page.get_by_role("button", name="Arm outputs locally").tap()
        close_runner_dialog(page, "phone-output-settings")
        page.get_by_role("button", name="Start locally").tap()
        gate = page.get_by_role("button", name="Continue", exact=True)
        context.route("**/participant-audit-spacing.css", lambda route: route.fulfill(
            content_type="text/css",
            body="#phone-response-instruction, #participant-continue, #participant-stop { "
                 "font-size: 200% !important; line-height: 1.5 !important; "
                 "letter-spacing: .12em !important; word-spacing: .16em !important; }",
        ))
        for index in range(2):
            expect(gate).to_be_focused(timeout=15_000)
            expect(page.locator("#phone-response-instruction")).to_have_text("Continue to next stage")
            if index == 1:
                page.add_style_tag(url=f"{origin}/participant-audit-spacing.css")
                page.screenshot(path=ARTIFACTS / "participant-gate-320-text-spacing.png")
            assert page.locator("#phone-participant-view").evaluate(
                """(node) => {
                    const prompt = node.querySelector('#phone-response-instruction').getBoundingClientRect();
                    const actions = node.querySelector('.participant-actions').getBoundingClientRect();
                    return node.scrollWidth <= node.clientWidth && node.scrollHeight <= node.clientHeight &&
                        node.contains(document.elementFromPoint(innerWidth / 2, 12)) &&
                        prompt.top >= 0 && prompt.bottom <= actions.top;
                }"""
            )
            gate.press("Enter")
        expect(page.locator("#phone-run-state")).to_have_text("Completed")
        expect(page.locator("#phone-timeline-list")).to_contain_text("Vibration requested")
        with page.expect_download() as download:
            page.get_by_role("button", name="Download event log").click()
        exported = json.loads(download.value.path().read_text(encoding="utf-8"))
        assert [trial["number"] for trial in exported["trials"]] == [1, 2, 3]
        assert all(trial["vibration_lateness_ms"] is not None for trial in exported["trials"])
        # The two arming attempts and the three scheduled cues request 100 ms each.
        assert page.evaluate("ppsVibrationCalls.filter(value => value > 0)") == [100] * 5
        assert not errors, errors
        print("Local phone study, refused-vibration handling, two instruction gates and JSON export passed.")


def audit_phone_catalogue(browser, origin):
    expected = json.loads((PAGES / "assets" / "phone-studies" / "index.json").read_text(encoding="utf-8"))
    with browser.new_context(viewport={"width": 320, "height": 780}, has_touch=True) as context:
        context.add_init_script("Object.defineProperty(navigator, 'vibrate', { value: () => true });")
        page = context.new_page()
        page.goto(f"{origin}/experiment-runner/")
        open_runner_dialog(page, "phone-study-settings")
        selection = page.locator("#phone-study")
        expect(selection.locator("option")).to_have_count(len(expected) + 1)
        for study in expected:
            selection.select_option(study["id"])
            page.get_by_role("button", name="Prepare study", exact=True).click()
            expect(page.locator("#phone-run-state")).to_have_text("Prepared")
            assert not page.locator("#phone-participant-view").is_visible()
        print(f"Prepared all {len(expected)} phone catalogue profiles in Chromium.")


def audit_live_beacon(browser, origin, study=None, complete_fixture=False, full_study=False):
    # Two independent browser contexts. Only the physical vibration API is instrumented.
    with browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True) as target_context, browser.new_context() as controller_context:
        target_context.add_init_script("""
          window.ppsVibrationCalls = [];
          window.ppsCueMs = null;
          Object.defineProperty(navigator, 'vibrate', { value: (value) => {
            ppsVibrationCalls.push(value);
            if (Array.isArray(value) || value > 30) ppsCueMs = performance.now();
            return true;
          }});
        """)
        if complete_fixture:
            study = stage_completion_fixture(target_context)
        target = target_context.new_page()
        controller = controller_context.new_page()
        target.goto(f"{origin}/experiment-runner/")
        controller.goto(f"{origin}/experiment-runner/")
        open_runner_dialog(target, "remote-center")
        target.locator("#target-beacon-start").click()
        expect(target.locator("#target-beacon-status")).to_have_text("Advertising", timeout=25000)
        open_runner_dialog(controller, "remote-center")
        controller.get_by_role("button", name="Scan for a beacon").click()
        controller.locator("#beacon-browse").click()
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
        close_runner_dialog(controller, "remote-center")
        close_runner_dialog(target, "remote-center")
        expect(controller.get_by_role("button", name="Start part")).to_be_disabled()
        open_runner_dialog(target, "phone-study-settings")
        target.get_by_role("button", name="Submit setup").click()
        if study:
            target.locator("#phone-study").select_option(study)
            target.get_by_role("button", name="Prepare study", exact=True).click()
            expect(controller.locator("#controller-study")).to_be_visible()
        else:
            controller.get_by_role("button", name="Prepare demo").click()
        expect(controller.get_by_role("button", name="Start part")).to_be_disabled()
        close_runner_dialog(target, "phone-study-settings")
        open_runner_dialog(target, "phone-output-settings")
        target.get_by_role("button", name="Arm outputs locally").click()
        close_runner_dialog(target, "phone-output-settings")
        expect(controller.get_by_role("button", name="Start part")).to_be_enabled(timeout=12000)
        target.evaluate("ppsCueMs = null")
        controller.get_by_role("button", name="Start part").click()
        surface = target.locator("#phone-response")
        expect(surface).to_be_visible(timeout=12000)
        assert surface.evaluate("(node) => node.scrollWidth <= node.clientWidth && node.scrollHeight <= node.clientHeight")
        target.screenshot(path=ARTIFACTS / "participant-during-run.png")
        if complete_fixture:
            expect(controller.locator("#controller-timeline-list")).to_contain_text("Audio scheduled")
            assert target.evaluate("ppsCueMs === null"), "The controller did not show the audio until vibration"
        if full_study:
            expect(controller.locator("#controller-timeline-list")).to_contain_text("Vibration requested", timeout=10000)
        else:
            surface.tap()
            if complete_fixture:
                bounds = surface.bounding_box()
                center = {"x": bounds["x"] + bounds["width"] / 2, "y": bounds["y"] + bounds["height"] / 2}
                touch = target_context.new_cdp_session(target)
                target.wait_for_function("() => ppsCueMs !== null && performance.now() - ppsCueMs >= 1900", timeout=7000)
                touch.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [center]})
                target.wait_for_function("() => performance.now() - ppsCueMs >= 2130")
                touch.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            else:
                target.wait_for_function("() => ppsCueMs !== null && performance.now() - ppsCueMs >= 1450", timeout=7000)
                surface.tap()
                surface.tap()
            timeline = controller.locator("#controller-timeline-list")
            expect(timeline).to_contain_text("Audio scheduled")
            expect(timeline).to_contain_text("Vibration requested")
            responses = timeline.get_by_role("listitem").filter(has_text=" ms RT")
            expect(responses).to_have_count(1)
            reaction_time = int(re.search(r"(\d+) ms RT", responses.inner_text())[1])
            assert (1850 if complete_fixture else 1300) < reaction_time <= 2000, reaction_time
        if study:
            if complete_fixture:
                expect(controller.locator("#controller-run-state")).to_have_text("Instruction Gate", timeout=15000)
                previous_cue = target.evaluate("ppsCueMs")
                controller.get_by_role("button", name="Continue", exact=True).click()
                trial_number = controller.locator("#controller-trial-number")
                expect(trial_number).to_have_text("Trial 3", timeout=10000)
                target.wait_for_function(
                    "(previousCue) => ppsCueMs > previousCue && performance.now() - ppsCueMs >= 1450",
                    arg=previous_cue, timeout=7000,
                )
                surface.tap()
                summary = controller.locator("#controller-recent-trials summary")
                summary.press("Enter")
                expect(summary).to_be_focused()
                history = controller.locator("#controller-recent-trial-list")
                earlier = history.get_by_role("listitem").filter(has_text="Trial 2")
                expect(earlier).to_contain_text("Audio scheduled")
                expect(earlier).to_contain_text("Vibration requested")
                expect(earlier).to_contain_text("ms RT")
                earlier_rt = int(re.search(r"(\d+) ms RT", earlier.inner_text())[1])
                assert 1300 < earlier_rt <= 2000
                expect(trial_number).to_have_text("Trial 3")

                controller.set_viewport_size({"width": 320, "height": 800})
                controller_context.route("**/timeline-audit-spacing.css", lambda route: route.fulfill(
                    content_type="text/css",
                    body=".browser-timeline * { line-height: 1.5 !important; letter-spacing: .12em !important; word-spacing: .16em !important; }",
                ))
                controller.add_style_tag(url=f"{origin}/timeline-audit-spacing.css")
                history.scroll_into_view_if_needed()
                assert history.evaluate("(node) => node.scrollWidth <= node.clientWidth")
                assert controller.evaluate("document.documentElement.scrollWidth <= innerWidth")
                controller.locator("#controller-timeline").screenshot(path=ARTIFACTS / "controller-timeline-320.png")
                expect(controller.locator("#controller-run-state")).to_have_text("Instruction Gate", timeout=15000)
                controller.get_by_role("button", name="Continue", exact=True).click()
                expect(target.locator("#phone-run-state")).to_have_text("Completed", timeout=6000)
            elif full_study:
                expect(target.locator("#phone-run-state")).to_have_text("Completed", timeout=90000)
            else:
                target.get_by_role("button", name="Stop experiment").click()
                expect(target.locator("#phone-run-state")).to_have_text("Interrupted", timeout=6000)
            with target.expect_download() as download:
                target.get_by_role("button", name="Download event log").click()
            exported = json.loads(download.value.path().read_text(encoding="utf-8"))
            assert exported["final_snapshot"]["browser_study"]["id"] == study
            if full_study:
                expected = exported["final_snapshot"]["browser_study"]["trial_count"]
                assert len(exported["trials"]) == expected
                assert [trial["number"] for trial in exported["trials"]] == list(range(1, expected + 1))
                print(f"Completed {expected} trials for {study}.")
            else:
                assert exported["trials"][0]["rt_ms"] == reaction_time
            if complete_fixture:
                assert [trial["rt_ms"] for trial in exported["trials"]] == [reaction_time, earlier_rt, None]
                print(f"Controller and export recorded a {reaction_time} ms tap released after the deadline.")
                print(f"Trial 2 retained its {earlier_rt} ms tap while Trial 3 stayed on the current timeline.")
        else:
            expect(target.locator("#phone-run-state")).to_have_text("Completed", timeout=6000)
        open_runner_dialog(target, "remote-center")
        target.get_by_role("button", name="Disconnect controller").click()
        expect(controller.get_by_role("button", name="Start part")).to_be_hidden(timeout=15000)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", action="store_true", help="use installed Google Chrome")
    parser.add_argument("--origin", help="check the assembled content at a deployed origin")
    parser.add_argument("--live-beacon", action="store_true", help="also use the live VDO.Ninja service")
    parser.add_argument("--runner-only", action="store_true", help="skip the install and cached study audit")
    parser.add_argument("--study", help="prepared browser study ID staged under assets/phone-studies")
    parser.add_argument("--complete-fixture", action="store_true", help="complete the two-block instruction fixture")
    parser.add_argument("--full-study", action="store_true", help="wait for completion of a short prepared study")
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
                browser = playwright.chromium.launch(channel="chrome" if args.chrome else None)
                try:
                    origin = args.origin or f"http://127.0.0.1:{server.server_port}"
                    if not args.runner_only and not args.origin:
                        audit(browser, origin, server)
                    audit_shared_shell(browser, origin)
                    audit_routes(browser, origin)
                    print("Shared page shell, Downloads, top-level Runner navigation, and the local browser demo passed.")
                    audit_phone_catalogue(browser, origin)
                    audit_local_phone_study(browser, origin)
                    if args.live_beacon:
                        audit_live_beacon(browser, origin, args.study, args.complete_fixture, args.full_study)
                        print("Live two-browser beacon pairing and remote start passed.")
                finally:
                    browser.close()
        finally:
            server.shutdown()
            thread.join()
    if not args.runner_only and not args.origin:
        print("Online refresh, keyboard playback, Chromium installability and offline Study 5 passed.")


if __name__ == "__main__":
    main()
