"""Compiled output-setup controls with mocked native authority; no hardware proof."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from run_bounded_text_audit import serve_repository
from run_runner_participant_ui_audit import BRIDGE


OUTPUT_BRIDGE = """() => {
  const state = window.outputAudit = {requests:[], hold:false, reject:false, noMatch:false,mediaPrepared:false};
  const participant = window.participantAudit;
  participant.snapshot.run.phase='prepared';
  participant.snapshot.run.participant_capture_ready=false;
  participant.snapshot.safety.local_armed=false;
  participant.snapshot.safety.capture_started=false;
  participant.snapshot.setup.ready=true;
  participant.snapshot.allowed_actions=['system.snapshot','target.disarm'];
  state.status = {schema:'pps-runner-native-output-preflight.v1',phase:'idle',
    policyGeneration:'1',serviceGeneration:'1',operationGeneration:'0',
    inventoryGeneration:null,reservationGeneration:null,inFlight:false,cleanupPending:false,
    silenceOnly:true,mediaConnected:false,armed:false,executable:false,qualified:false,lastErrorCode:null};
  const invoke = window.__TAURI_INTERNALS__.invoke;
  const clone = value => structuredClone(value);
  window.__TAURI_INTERNALS__.invoke = async (command, args) => {
    if (command === 'select_prepared_session') return {snapshot:clone(participant.snapshot),
      summary:{sessionId:'synthetic-ui-session',executionMode:'synthetic-only',
        blocks:[{index:1,label:'Synthetic block',trialCount:1,durationS:1}]}};
    if (command === 'inspect_prepared_execution') return {inspectionScope:'schedule-only',
      timingQualification:'unqualified',executable:false,blockCount:1,trialRowCount:1,
      eventCount:2,encodedBytes:500,blocks:[{}]};
    if (command === 'prepare_first_audio_block') {state.mediaPrepared=true; return {schema:'pps-runner-prepared-audio-summary.v1',
      preparationScope:'pcm-and-output-plan-cache',outputQualification:'unqualified',
      executable:false,outputPlanPrepared:true,outputRoute:'canonical-three',scheduledEventCount:2,
      blockOrdinal:0,sampleRateHz:48000,sourceChannels:3,sourceChannelLayout:'binaural-left-right-tactile',
      frames:48000,decodedBytes:576000,cacheCapacityBlocks:1,cacheByteBudget:1280*1024*1024};}
    if (command === 'native_output_status') return clone(state.status);
    if (command === 'native_output_enumerate') {
      state.requests.push({command});
      state.status.phase='enumerated'; state.status.operationGeneration='1';
      state.status.inventoryGeneration='9007199254740993';
      return {schema:'pps-runner-native-output-inventory.v2',
        policyGeneration:state.status.policyGeneration,serviceGeneration:'1',
        inventoryGeneration:state.status.inventoryGeneration,executable:false,qualified:false,armed:false,
        devices:[{deviceOrdinal:0,displayName:'Laborgerät für Audio und Taktile Ausgabe '+ 'LangerGerätename'.repeat(7),
          outputConfigs:[{configOrdinal:0,channels:2,sampleFormat:'f32',minimumSampleRateHz:44100,maximumSampleRateHz:48000},
            {configOrdinal:1,channels:3,sampleFormat:'i32',minimumSampleRateHz:44100,maximumSampleRateHz:44100},
            {configOrdinal:2,channels:state.noMatch ? 2 : 3,sampleFormat:'i32',minimumSampleRateHz:48000,maximumSampleRateHz:96000}]}]};
    }
    if (command === 'native_output_reserve_silence') {
      if (!state.mediaPrepared) throw new Error('Synthetic native cache has been retired');
      state.requests.push({command,request:clone(args.request)});
      state.status.phase='reserved-media'; state.status.operationGeneration='2';
      state.status.reservationGeneration='7'; state.status.mediaConnected=true;
      const result=clone(state.status);
      if (state.hold) return new Promise(resolve => {state.resolveReserve=()=>resolve(result);});
      if (state.reject) {state.reject=false; throw {code:'native_output_timeout',message:'Synthetic lost preparation acknowledgement'};}
      return result;
    }
    if (command === 'activate_native_execution') {
      state.requests.push({command,request:clone(args.request)});
      if (state.status.phase !== 'reserved-media' || state.status.executable
          || args.request.acknowledgeUnqualified !== true) {
        throw {code:'native_execution_scope_invalid',message:'Synthetic activation denied'};
      }
      state.status.executable=true;
      participant.snapshot.safety.audio_route_ready=true;
      participant.snapshot.timing_tier='native_desktop_unqualified';
      participant.snapshot.allowed_actions.push('target.arm');
      participant.snapshot.revision++;
      participant.emit(participant.snapshot);
      return clone(participant.snapshot);
    }
    if (command === 'native_output_release' || command === 'native_output_disable') {
      state.requests.push({command,...(args ? {request:clone(args.request)} : {})});
      state.status.policyGeneration=String(BigInt(state.status.policyGeneration)+1n);
      state.status.phase=command === 'native_output_disable' ? 'disabled' : 'idle';
      state.status.inventoryGeneration=null; state.status.reservationGeneration=null;
      state.status.mediaConnected=false;
      state.status.executable=false;
      state.mediaPrepared=false;
      return clone(state.status);
    }
    return invoke(command,args);
  };
}"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/runner-output-ui-audit"))
    output = parser.parse_args().output_dir
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    with serve_repository() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--disk-cache-size=1048576"])
        preview = browser.new_page(viewport={"width": 320, "height": 800})
        preview.goto(f"{base}/apps/runner/compiled/index.html", wait_until="networkidle")
        for name in ("list", "route", "prepare", "release", "disable"):
            assert preview.locator(f"#native-output-{name}").is_disabled()
        assert preview.locator("#native-execution-activate").is_disabled()
        assert preview.locator("#native-execution-acknowledgement").is_disabled()
        preview.close()
        page = browser.new_page()
        page.add_init_script(script=f"({BRIDGE})(); ({OUTPUT_BRIDGE})()")
        page.goto(f"{base}/apps/runner/compiled/index.html", wait_until="networkidle")
        listing = page.locator("#native-output-list")
        route = page.locator("#native-output-route")
        prepare = page.locator("#native-output-prepare")
        activate = page.locator("#native-execution-activate")
        acknowledgement = page.locator("#native-execution-acknowledgement")
        detail = page.locator("#native-output-detail")
        assert listing.is_disabled()
        page.locator("#select-session-manifest").click()
        page.locator("#inspect-prepared-execution").click()
        page.locator("#prepare-first-audio-block").click()
        page.wait_for_function("!document.querySelector('#native-output-list').disabled")
        listing.click()
        page.wait_for_function("document.querySelector('#native-output-route').options.length === 2")
        assert prepare.is_disabled(), "Device choice must be explicit"
        route.select_option("0")
        assert prepare.is_enabled()
        for width, height, enlarged in [(320,800,False),(390,844,False),(844,390,False),
                                        (1440,900,False),(1920,1080,False),(320,800,True)]:
            page.set_viewport_size({"width":width,"height":height})
            if enlarged:
                page.evaluate("""() => {
                  document.documentElement.style.fontSize='32px';
                  document.querySelector('#native-output-prepare').textContent='Audioausgabe für das vorbereitete Experiment stumm vorbereiten';
                  for (const node of document.querySelectorAll('*')) {
                    node.style.letterSpacing='0.12em'; node.style.wordSpacing='0.16em';
                  }
                }""")
            prepare.scroll_into_view_if_needed()
            page.wait_for_timeout(150)
            geometry = prepare.evaluate("""node => ({width:node.clientWidth,scroll:node.scrollWidth,
              height:node.clientHeight,scrollHeight:node.scrollHeight,measured:node.dataset.pretextResult,
              pageWidth:document.documentElement.clientWidth,pageScroll:document.documentElement.scrollWidth})""")
            assert geometry["measured"] not in {None,"unavailable"}, geometry
            assert geometry["scroll"] <= geometry["width"] + 1, geometry
            assert geometry["scrollHeight"] <= geometry["height"] + 1, geometry
            assert geometry["pageScroll"] <= geometry["pageWidth"] + 1, geometry
            label = page.locator(".check-row > span[data-pretext]")
            label_geometry = label.evaluate("""node => ({width:node.clientWidth,scroll:node.scrollWidth,
              height:node.clientHeight,scrollHeight:node.scrollHeight,measured:node.dataset.pretextResult})""")
            assert label_geometry["measured"] not in {None,"unavailable","no-fit"}, label_geometry
            assert label_geometry["scroll"] <= label_geometry["width"] + 1, label_geometry
            assert label_geometry["scrollHeight"] <= label_geometry["height"] + 1, label_geometry
            assert page.locator("#toast").evaluate("node => getComputedStyle(node).position === 'static'")
            page.screenshot(path=str(output / f"output-{width}-{'enlarged' if enlarged else height}.png"))
            cases.append({"viewport":[width,height],"enlarged":enlarged,**geometry})
        prepare.focus()
        prepare.press("Space")
        page.wait_for_function("window.outputAudit.requests.some(r => r.command==='native_output_reserve_silence')")
        page.wait_for_function("document.querySelector('#native-output-detail').textContent.startsWith('Prepared and silent')")
        request = page.evaluate("window.outputAudit.requests.find(r => r.request)?.request")
        assert request == {"policyGeneration":"1","serviceGeneration":"1","inventoryGeneration":"9007199254740993",
                           "deviceOrdinal":0,"configOrdinal":2,"channels":3,"sampleRateHz":48000,
                           "bufferFrames":None,"warmupTimeoutMs":3000}, request
        assert page.locator("#prepared-audio-status").inner_text() == "Prepared · output reserved"
        assert acknowledgement.is_enabled() and activate.is_disabled()
        acknowledgement.check()
        assert activate.is_enabled()
        activate.click()
        page.wait_for_function("document.querySelector('#native-output-detail').textContent.startsWith('Native run enabled')")
        activation = page.evaluate("window.outputAudit.requests.find(r => r.command==='activate_native_execution').request")
        assert activation == {"reservation":{"policyGeneration":"1","serviceGeneration":"1",
                       "reservationGeneration":"7"},"acknowledgeUnqualified":True}, activation
        assert not acknowledgement.is_checked() and activate.is_disabled()
        assert page.locator("#prepared-audio-status").inner_text() == "Prepared · native run enabled"
        assert page.locator("#participant-response").is_disabled()
        page.screenshot(path=str(output / "activated-320-enlarged.png"))
        page.locator("#native-output-release").click()
        page.wait_for_function("document.querySelector('#native-output-route').options.length === 1")
        assert listing.is_disabled(), "Release must retire the cached media summary"
        page.locator("#prepare-first-audio-block").click()
        page.wait_for_function("!document.querySelector('#native-output-list').disabled")
        listing.click()
        page.wait_for_function("document.querySelector('#native-output-route').options.length === 2")
        route.select_option("0")
        page.evaluate("window.outputAudit.hold = true")
        prepare.click()
        page.wait_for_function("typeof window.outputAudit.resolveReserve === 'function'")
        assert page.locator("#native-output-disable").is_enabled()
        page.locator("#native-output-disable").click()
        page.wait_for_function("window.outputAudit.status.phase === 'disabled'")
        page.evaluate("window.outputAudit.resolveReserve(); window.outputAudit.hold = false")
        page.wait_for_timeout(1200)
        assert not detail.inner_text().startswith("Prepared and silent"), "Late reservation must not restore disabled output"
        assert prepare.is_disabled() and page.locator("#native-output-release").is_disabled()
        assert listing.is_disabled(), "Disable must require fresh media preparation"
        page.locator("#prepare-first-audio-block").click()
        page.wait_for_function("!document.querySelector('#native-output-list').disabled")
        page.evaluate("window.outputAudit.noMatch = true")
        listing.click()
        page.wait_for_function("document.querySelector('#native-output-detail').textContent.startsWith('No listed configuration')")
        assert route.locator("option").count() == 1 and prepare.is_disabled()
        page.evaluate("window.outputAudit.noMatch = false")
        listing.click()
        page.wait_for_function("document.querySelector('#native-output-route').options.length === 2")
        route.select_option("0")
        page.evaluate("window.outputAudit.reject = true")
        prepare.click()
        page.wait_for_function("document.querySelector('#native-output-detail').textContent.startsWith('Prepared and silent')")
        page.wait_for_timeout(1200)
        requests = page.evaluate("window.outputAudit.requests")
        assert sum(request["command"] == "native_output_reserve_silence" for request in requests) == 3
        assert page.locator("#participant-response").is_disabled()
        page.locator("#native-output-release").click()
        page.locator("#prepare-first-audio-block").click()
        page.wait_for_function("!document.querySelector('#native-output-list').disabled")
        listing.click()
        page.wait_for_function("document.querySelector('#native-output-route').options.length === 2")
        route.select_option("0")
        page.evaluate("window.outputAudit.status.inventoryGeneration = '9007199254740994'")
        page.wait_for_function("document.querySelector('#native-output-route').options.length === 1")
        assert prepare.is_disabled(), "Changed inventory must invalidate the choice"
        listing.click()
        page.wait_for_function("document.querySelector('#native-output-route').options.length === 2")
        route.select_option("0")
        page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted:true}))")
        assert listing.is_disabled() and prepare.is_disabled()
        page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true}))")
        page.wait_for_function("!document.querySelector('#native-output-list').disabled")
        assert prepare.is_disabled() and route.locator("option").count() == 1
        page.evaluate("""() => {
          const state = window.participantAudit;
          state.snapshot.run.phase='unknown'; state.snapshot.revision++; state.emit(state.snapshot);
        }""")
        assert listing.is_disabled(), "Unknown phase must not authorize device setup"
        page.evaluate("""() => {
          const state = window.participantAudit;
          state.snapshot.run.phase='prepared'; delete state.snapshot.safety.local_armed;
          state.snapshot.revision++; state.emit(state.snapshot);
        }""")
        assert listing.is_disabled(), "Missing disarm evidence must not authorize device setup"
        browser.close()
    report = {"passed":True,"evidence":"compiled-browser-with-mocked-native-bridge",
              "installed_qualification":False,"physical_qualification":False,
              "cases":cases,"matching_config_only":True,"explicit_device_choice":True,
              "decimal_generation_preserved":True,"disable_cancels_pending_view":True,
              "lost_ack_not_replayed":True,"changed_inventory_invalidates_choice":True,
              "resume_requires_fresh_inventory":True,
              "unknown_phase_and_missing_disarm_disabled":True,
              "release_and_disable_retire_media_summary":True,
              "preparation_never_enables_acquisition":True,
              "explicit_native_activation_fenced_and_unqualified":True}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Passed {len(cases)} rendered output layouts and native preflight control cases; {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
