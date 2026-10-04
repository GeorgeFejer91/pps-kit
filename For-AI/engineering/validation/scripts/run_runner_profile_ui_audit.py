"""Rendered compiled Runner profile controls with a mocked native boundary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from run_bounded_text_audit import serve_repository
from run_runner_participant_ui_audit import BRIDGE


PROFILE_BRIDGE = """() => {
  const state = window.participantAudit;
  state.snapshot.run.phase = 'prepared';
  state.snapshot.run.participant_capture_ready = false;
  state.snapshot.package_verified = false;
  state.snapshot.package_label = 'No package loaded.';
  state.snapshot.setup.submitted = true;
  state.snapshot.setup.ready = true;
  state.snapshot.safety.local_armed = false;
  state.snapshot.safety.capture_started = false;
  state.snapshot.allowed_actions = ['system.snapshot'];
  state.snapshot.active_block.active = false;
  state.snapshot.identity.session_id = '';
  state.profileCalls = [];
  state.cancelNextProfile = true;
  const invoke = window.__TAURI_INTERNALS__.invoke;
  window.__TAURI_INTERNALS__.invoke = async (command, args) => {
    if (command !== 'prepare_experiment_profile') return invoke(command, args);
    state.profileCalls.push({command, args: args ?? null});
    if (state.cancelNextProfile) {
      state.cancelNextProfile = false;
      return {cancelled: true, summary: null, snapshot: structuredClone(state.snapshot)};
    }
    state.snapshot.package_verified = true;
    state.snapshot.package_label = 'P001 · 8 blocks · verified V1 plan';
    state.snapshot.identity.session_id = 'P001_visual_fixture';
    state.snapshot.revision++;
    return {
      cancelled: false,
      snapshot: structuredClone(state.snapshot),
      summary: {
        schema: 'pps-run-session.v1', participantId: 'P001',
        sessionId: 'P001_visual_fixture', executionMode: 'participant_block_wavs',
        blocks: Array.from({length: 8}, (_, index) => ({
          index: index + 1,
          label: `Geprüfter audiotaktiler Versuchsblock ${index + 1} mit ausführlicher Quellenbezeichnung`,
          trialCount: 8, durationS: 8
        }))
      }
    };
  };
}"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/runner-profile-ui-audit"))
    output = parser.parse_args().output_dir
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    with serve_repository() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 900, "height": 620})
        page.add_init_script(script=f"({BRIDGE})(); ({PROFILE_BRIDGE})()")
        page.goto(f"{base}/apps/runner/compiled/index.html", wait_until="networkidle")
        prepare = page.locator("#prepare-experiment-profile")
        manifest = page.locator("#select-session-manifest")
        next_audio = page.locator("#prepare-current-audio-block")
        assert prepare.is_enabled() and manifest.is_enabled()
        assert next_audio.is_visible() and next_audio.is_disabled()
        prepare.click()
        page.wait_for_function("window.participantAudit.profileCalls.length === 1")
        page.wait_for_function("!document.querySelector('#prepare-experiment-profile').disabled")
        assert prepare.is_enabled() and not page.locator("#package-block-list li").count()
        prepare.click()
        page.wait_for_function("document.querySelectorAll('#package-block-list li').length === 8")
        page.wait_for_function("!document.querySelector('#prepare-experiment-profile').disabled")
        assert prepare.is_enabled() and manifest.is_enabled()
        assert page.evaluate("window.participantAudit.profileCalls") == [
            {"command": "prepare_experiment_profile", "args": {}},
            {"command": "prepare_experiment_profile", "args": {}},
        ]

        for width, height, enlarged in [
            (320, 800, False), (900, 620, False), (1000, 620, False),
            (1440, 900, False), (1440, 1100, False), (320, 800, True),
        ]:
            page.set_viewport_size({"width": width, "height": height})
            if enlarged:
                page.evaluate("""() => {
                  document.documentElement.style.fontSize = '32px';
                  document.querySelector('#prepare-experiment-profile').textContent =
                    'Geprüftes Experimentprofil mit vollständig erhaltenen Audiodateien vorbereiten';
                  document.querySelector('#select-session-manifest').textContent =
                    'Vorbereitetes Experimentmanifest aus dem lokalen Ordner auswählen';
                  for (const node of document.querySelectorAll('*')) {
                    node.style.letterSpacing = '0.12em'; node.style.wordSpacing = '0.16em';
                  }
                }""")
            prepare.scroll_into_view_if_needed()
            page.wait_for_timeout(180)
            geometry = page.locator(".package-panel").evaluate("""panel => {
              const actions = panel.querySelector('.package-actions');
              const buttons = [...actions.querySelectorAll('button')];
              const heading = panel.querySelector('.section-heading');
              const list = panel.querySelector('#package-block-list');
              const nextAudio = panel.querySelector('#prepare-current-audio-block');
              const box = node => {
                const rect = node.getBoundingClientRect();
                return {left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom,
                  width: node.clientWidth, scrollWidth: node.scrollWidth,
                  height: node.clientHeight, scrollHeight: node.scrollHeight,
                  measured: node.dataset.pretextResult ?? null};
              };
              return {panel: box(panel), heading: box(heading), actions: box(actions),
                nextAudio: box(nextAudio),
                buttons: buttons.map(box), list: box(list), listOverflow: getComputedStyle(list).overflowY,
                pageWidth: document.documentElement.clientWidth,
                pageScrollWidth: document.documentElement.scrollWidth};
            }""")
            name = f"profile-{width}-{height}{'-enlarged' if enlarged else ''}"
            page.screenshot(path=str(output / f"{name}.png"), full_page=True)
            assert geometry["pageScrollWidth"] <= geometry["pageWidth"] + 1, geometry
            assert geometry["panel"]["scrollWidth"] <= geometry["panel"]["width"] + 1, geometry
            assert geometry["panel"]["scrollHeight"] <= geometry["panel"]["height"] + 1, geometry
            assert geometry["listOverflow"] == "visible", geometry
            assert geometry["list"]["scrollHeight"] <= geometry["list"]["height"] + 1, geometry
            assert geometry["heading"]["bottom"] < geometry["actions"]["top"], geometry
            first, second = geometry["buttons"]
            assert first["bottom"] <= second["top"] and abs(first["width"] - second["width"]) <= 1, geometry
            for button in geometry["buttons"]:
                assert button["measured"] not in {None, "unavailable", "no-fit"}, geometry
                assert button["scrollWidth"] <= button["width"] + 1, geometry
                assert button["scrollHeight"] <= button["height"] + 1, geometry
            next_geometry = geometry["nextAudio"]
            assert next_geometry["measured"] not in {None, "unavailable", "no-fit"}, geometry
            assert next_geometry["scrollWidth"] <= next_geometry["width"] + 1, geometry
            assert next_geometry["scrollHeight"] <= next_geometry["height"] + 1, geometry
            cases.append({"viewport": [width, height], "enlarged": enlarged, **geometry})
        browser.close()
    report = {"passed": True, "evidence": "compiled-browser-with-mocked-native-bridge",
              "installed_qualification": False, "physical_qualification": False,
              "profile_calls_without_paths": 2, "cases": cases}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Passed {len(cases)} rendered Runner profile layouts and native-bridge interactions; {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
