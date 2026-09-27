"""Rendered compiled participant-input checks; the native bridge is mocked."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from run_bounded_text_audit import serve_repository


BRIDGE = """() => {
  const callbacks = new Map(); let callbackId = 0; let listenerId = null;
  const state = window.participantAudit = {
    requests: [], failNext: false,
    snapshot: {
      epoch: 7, revision: 10, package_verified: true, package_label: 'Synthetic UI fixture',
      run: {phase: 'running', state_label: 'Running', progress_label: 'Block 1 / 1',
        event_label: 'Software fixture only', participant_capture_ready: true},
      identity: {session_id: 'synthetic-ui-session'}, part: {selected_part: 1},
      setup: {participant_code: 'P001', part_labels: {'1':'A','2':'B'}},
      safety: {local_armed: true, capture_started: true},
      active_block: {active: true, block_label: 'Synthetic fixture', duration_s: 2},
      allowed_actions: ['system.snapshot','run.pause','run.stop']
    },
    emit(snapshot) { callbacks.get(listenerId)?.({event:'runner-snapshot',id:1,payload:structuredClone(snapshot)}); }
  };
  window.__TAURI_EVENT_PLUGIN_INTERNALS__ = {unregisterListener() { listenerId = null; }};
  window.__TAURI_INTERNALS__ = {
    transformCallback(callback) { callbacks.set(++callbackId, callback); return callbackId; },
    async invoke(command, args) {
      if (command === 'plugin:event|listen') { listenerId = args.handler; return 1; }
      if (command === 'plugin:event|unlisten') return;
      if (command === 'runner_snapshot') return structuredClone(state.snapshot);
      if (command === 'remote_status') return {enabled:false,controllerConnected:false};
      if (command === 'runner_record_response') {
        state.requests.push(structuredClone(args.request));
        if (state.failNext) {state.failNext=false; throw {code:'native_response_unavailable',message:'Synthetic input rejection'};}
        return state.requests.length;
      }
      throw new Error(`Unexpected native fixture command: ${command}`);
    }
  };
}"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/runner-participant-ui-audit"))
    output = parser.parse_args().output_dir
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    with serve_repository() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--disk-cache-size=1048576"])
        preview = browser.new_page(viewport={"width": 320, "height": 800})
        preview.goto(f"{base}/apps/runner/compiled/index.html", wait_until="networkidle")
        assert preview.locator("#participant-response").is_disabled()
        preview.close()
        page = browser.new_page()
        page.add_init_script(script=f"({BRIDGE})()")
        page.goto(f"{base}/apps/runner/compiled/index.html", wait_until="networkidle")
        target = page.locator("#participant-response")
        page.wait_for_function("!document.querySelector('#participant-response').disabled")
        for width, height, enlarged in [(320,800,False),(390,844,False),(844,390,False),
                                        (1440,900,False),(1920,1080,False),(320,800,True)]:
            page.set_viewport_size({"width": width, "height": height})
            if enlarged:
                page.evaluate("""() => {
                  document.documentElement.style.fontSize = '32px';
                  const target = document.querySelector('#participant-response');
                  target.textContent = 'Teilnehmerantwort im laufenden Experiment erfassen';
                  for (const node of document.querySelectorAll('*')) {
                    node.style.letterSpacing='0.12em'; node.style.wordSpacing='0.16em';
                  }
                }""")
            target.scroll_into_view_if_needed()
            page.wait_for_timeout(120)
            geometry = target.evaluate("""node => ({
              width:node.clientWidth,scroll:node.scrollWidth,height:node.clientHeight,scrollHeight:node.scrollHeight,
              measured:node.dataset.pretextResult,pageWidth:document.documentElement.clientWidth,
              pageScroll:document.documentElement.scrollWidth
            })""")
            assert geometry["measured"] not in {None,"unavailable"}, geometry
            assert geometry["scroll"] <= geometry["width"] + 1, geometry
            assert geometry["scrollHeight"] <= geometry["height"] + 1, geometry
            if geometry["pageScroll"] > geometry["pageWidth"] + 1:
                geometry["overflow"] = page.evaluate("""() => [...document.querySelectorAll('body *')]
                  .filter(node => node.getBoundingClientRect().right > 321 || node.scrollWidth > node.clientWidth + 1)
                  .map(node => ({id:node.id, tag:node.tagName,cls:node.className,width:node.clientWidth,
                    scroll:node.scrollWidth,text:node.textContent.slice(0,50)})).slice(0,24)""")
                page.screenshot(path=str(output / "layout-failure.png"))
            assert geometry["pageScroll"] <= geometry["pageWidth"] + 1, geometry
            page.screenshot(path=str(output / f"response-{width}-{'enlarged' if enlarged else height}.png"))
            cases.append({"viewport": [width,height], "enlarged": enlarged, **geometry})
        box = target.bounding_box()
        target.click(position={"x": box["width"] * .25, "y": box["height"] * .75})
        target.focus()
        target.press("Space")
        page.wait_for_function("window.participantAudit.requests.length === 2")
        requests = page.evaluate("window.participantAudit.requests")
        assert abs(requests[0]["x"] - .25) < .02 and abs(requests[0]["y"] - .75) < .02, requests
        assert requests[1] == {"choice":"", "x":None, "y":None}, requests
        assert all(set(request) == {"choice","x","y"} for request in requests), requests
        page.evaluate("window.participantAudit.failNext = true")
        target.click()
        page.wait_for_function("window.participantAudit.requests.length === 3")
        page.wait_for_timeout(1200)
        assert page.evaluate("window.participantAudit.requests.length") == 3
        page.evaluate("""() => {
          const state = window.participantAudit;
          const older = structuredClone(state.snapshot);
          state.snapshot.revision++; state.snapshot.run.phase='paused';
          state.snapshot.run.participant_capture_ready=false;
          state.emit(state.snapshot); state.emit(older);
        }""")
        assert target.is_disabled()
        page.evaluate("""() => {
          const state = window.participantAudit;
          state.snapshot.revision++; state.snapshot.run.phase='running';
          delete state.snapshot.run.participant_capture_ready;
          state.emit(state.snapshot);
        }""")
        assert target.is_disabled(), "Older snapshots must not enable native acquisition"
        browser.close()
    report = {"passed":True, "evidence":"compiled-browser-with-mocked-native-bridge",
              "installed_qualification":False, "physical_qualification":False,
              "ordinary_browser_acquisition":False, "input_requests":3,
              "no_replay_on_rejection":True, "stale_and_missing_capture_state_disabled":True,
              "cases":cases}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Passed {len(cases)} rendered layouts and participant input/state checks; {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
