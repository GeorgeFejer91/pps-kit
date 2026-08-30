use std::{
    sync::{Mutex, OnceLock},
    time::{Instant, SystemTime, UNIX_EPOCH},
};

use jni::objects::{JObject, JString};
use jni::sys::jstring;
use jni::JNIEnv;
use pps_contracts::{
    Action, AppliedStatus, ClockStamp, RunnerPhase, TimingTier, JSON_MAX_SAFE_INTEGER,
};
use pps_runner_core::RunnerCore;
use serde_json::{json, Value};

mod relay;

use relay::{RelayAuthority, RelayOutcome};

const SNAPSHOT_SCHEMA: &str = "pps-quest-runner-snapshot.v1";
const PAIRING_SCHEMA: &str = "pps-quest-relay-pairing.v1";
const RELAY_RESULT_SCHEMA: &str = "pps-quest-relay-result.v1";
const TARGET_ID: &str = "pps-quest-local-preview";

struct QuestRunnerAdapter {
    core: RunnerCore,
    relay: RelayAuthority,
    message: String,
}

impl Default for QuestRunnerAdapter {
    fn default() -> Self {
        let mut core = RunnerCore::new(
            TARGET_ID,
            "native-quest-spatial-preview",
            unix_ms().max(1),
            TimingTier::NativeQuestUnqualified,
            clock_stamp(),
        );
        core.dispatch_local(
            Action::PackagePrepareDemo,
            json!({"label": "Native Quest compatibility demo"}),
            clock_stamp(),
        );
        core.dispatch_local(
            Action::SetupSubmit,
            json!({
                "participant_code": "QUEST_PREVIEW",
                "age": 18,
                "handedness": "prefer_not_to_say",
                "gender": "prefer_not_to_say",
                "name_sharing_opt_in": false,
                "part_labels": {"1": "Quest demo", "2": "Quest demo repeat"}
            }),
            clock_stamp(),
        );
        Self {
            core,
            relay: RelayAuthority::default(),
            message: "Shared PPS Rust authority ready; local arm is required.".to_owned(),
        }
    }
}

impl QuestRunnerAdapter {
    fn start_demo(&mut self) {
        match self.core.snapshot().run.phase {
            RunnerPhase::Ready => self.apply(Action::PartStart, json!({"part_number": 1})),
            RunnerPhase::Completed | RunnerPhase::Interrupted => {
                self.apply(
                    Action::PackagePrepareDemo,
                    json!({"label": "Native Quest compatibility demo"}),
                );
                self.message = "Demo prepared; press Arm locally before Start local.".to_owned();
            }
            RunnerPhase::Prepared => {
                self.message =
                    "start_demo rejected: target must be armed locally first.".to_owned();
            }
            RunnerPhase::Running => {
                self.message = "start_demo ignored while already running.".to_owned();
            }
            phase => self.message = format!("start_demo rejected while {phase:?}."),
        }
    }

    fn arm(&mut self) {
        self.apply(Action::TargetArm, json!({}));
    }

    fn disarm(&mut self) {
        self.apply(Action::TargetDisarm, json!({}));
    }

    fn pause(&mut self) {
        self.apply(Action::RunPause, json!({}));
    }

    fn resume(&mut self) {
        self.apply(Action::RunResume, json!({}));
    }

    fn stop(&mut self) {
        self.apply(Action::RunCompleteDemo, json!({}));
    }

    fn apply(&mut self, action: Action, args: Value) {
        let result = self.core.dispatch_local(action, args, clock_stamp());
        self.message = match result.status {
            AppliedStatus::Accepted | AppliedStatus::Duplicate => {
                format!("{}: {}.", action.as_str(), result.reason)
            }
            AppliedStatus::Rejected => {
                format!("{} rejected: {}.", action.as_str(), result.reason)
            }
        };
    }

    fn create_pairing_json(&mut self, companion_base_url: &str, room: &str) -> String {
        match self
            .relay
            .create_pairing(&mut self.core, companion_base_url, room)
        {
            Ok(pairing) => {
                self.message = "Canonical BRSP/1 invitation generated locally.".to_owned();
                json!({
                    "schema": PAIRING_SCHEMA,
                    "ok": true,
                    "target_id": pairing.target_id,
                    "session_id": pairing.session_id,
                    "room": pairing.room,
                    "secret": pairing.secret,
                    "invitation": pairing.invitation,
                    "scopes": pairing.scopes,
                    "error": "",
                })
                .to_string()
            }
            Err(error) => {
                self.message = error.clone();
                json!({
                    "schema": PAIRING_SCHEMA,
                    "ok": false,
                    "target_id": self.core.snapshot().target_id,
                    "session_id": "",
                    "room": room,
                    "secret": "",
                    "invitation": "",
                    "scopes": [],
                    "error": error,
                })
                .to_string()
            }
        }
    }

    fn begin_relay_json(&mut self, secret: &str) -> String {
        let outcome = self.relay.begin(&mut self.core, secret);
        self.finish_relay(outcome)
    }

    fn handle_relay_json(&mut self, frame: &str) -> String {
        let outcome = self.relay.handle_frame(&mut self.core, frame);
        self.finish_relay(outcome)
    }

    fn poll_relay_json(&mut self) -> String {
        let outcome = self.relay.poll(&mut self.core);
        self.finish_relay(outcome)
    }

    fn end_relay_json(&mut self, reason: &str) -> String {
        let outcome = self.relay.end(&mut self.core, reason);
        self.finish_relay(outcome)
    }

    fn finish_relay(&mut self, outcome: RelayOutcome) -> String {
        self.message = outcome.message.clone();
        json!({
            "schema": RELAY_RESULT_SCHEMA,
            "outbound": outcome.outbound,
            "refresh_ui": outcome.refresh_ui,
            "close": outcome.close,
            "phase": outcome.phase,
            "message": outcome.message,
        })
        .to_string()
    }

    fn snapshot_json(&self) -> String {
        let snapshot = self.core.snapshot();
        let state = match snapshot.run.phase {
            RunnerPhase::Running => "running",
            RunnerPhase::Paused | RunnerPhase::InstructionGate => "paused",
            RunnerPhase::Completed | RunnerPhase::Interrupted | RunnerPhase::Stopping => "stopped",
            RunnerPhase::Error => "error",
            RunnerPhase::Idle | RunnerPhase::Prepared | RunnerPhase::Ready => "ready",
        };
        json!({
            "schema": SNAPSHOT_SCHEMA,
            "state": state,
            "revision": snapshot.revision,
            "message": self.message,
            "core": "shared-pps-runner-core",
            "armed": snapshot.safety.local_armed,
            "connection_state": snapshot.connection_state,
        })
        .to_string()
    }
}

static RUNNER: OnceLock<Mutex<QuestRunnerAdapter>> = OnceLock::new();
static CLOCK_START: OnceLock<Instant> = OnceLock::new();

fn clock_stamp() -> ClockStamp {
    let started = CLOCK_START.get_or_init(Instant::now);
    ClockStamp {
        unix_ms: unix_ms(),
        monotonic_ns: started
            .elapsed()
            .as_nanos()
            .min(JSON_MAX_SAFE_INTEGER as u128) as u64,
    }
}

fn unix_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis().min(JSON_MAX_SAFE_INTEGER as u128) as u64)
        .unwrap_or_default()
}

fn with_runner<T>(mutator: impl FnOnce(&mut QuestRunnerAdapter) -> T) -> T {
    let mutex = RUNNER.get_or_init(|| Mutex::new(QuestRunnerAdapter::default()));
    let mut runner = match mutex.lock() {
        Ok(guard) => guard,
        Err(poisoned) => poisoned.into_inner(),
    };
    mutator(&mut runner)
}

fn with_snapshot(mutator: impl FnOnce(&mut QuestRunnerAdapter)) -> String {
    with_runner(|runner| {
        mutator(runner);
        runner.snapshot_json()
    })
}

fn java_string(env: &mut JNIEnv<'_>, value: JString<'_>) -> String {
    env.get_string(&value).map(Into::into).unwrap_or_default()
}

fn to_java_string(env: &mut JNIEnv<'_>, payload: String) -> jstring {
    match env.new_string(payload) {
        Ok(value) => value.into_raw(),
        Err(_) => std::ptr::null_mut(),
    }
}

#[no_mangle]
pub extern "system" fn Java_io_ppskit_questrunner_core_JniBindings_nativeRequestSnapshot(
    mut env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    to_java_string(&mut env, with_snapshot(|_| {}))
}

#[no_mangle]
pub extern "system" fn Java_io_ppskit_questrunner_core_JniBindings_nativeStartDemo(
    mut env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    to_java_string(&mut env, with_snapshot(QuestRunnerAdapter::start_demo))
}

#[no_mangle]
pub extern "system" fn Java_io_ppskit_questrunner_core_JniBindings_nativeArmTarget(
    mut env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    to_java_string(&mut env, with_snapshot(QuestRunnerAdapter::arm))
}

#[no_mangle]
pub extern "system" fn Java_io_ppskit_questrunner_core_JniBindings_nativeDisarmTarget(
    mut env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    to_java_string(&mut env, with_snapshot(QuestRunnerAdapter::disarm))
}

#[no_mangle]
pub extern "system" fn Java_io_ppskit_questrunner_core_JniBindings_nativePause(
    mut env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    to_java_string(&mut env, with_snapshot(QuestRunnerAdapter::pause))
}

#[no_mangle]
pub extern "system" fn Java_io_ppskit_questrunner_core_JniBindings_nativeResume(
    mut env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    to_java_string(&mut env, with_snapshot(QuestRunnerAdapter::resume))
}

#[no_mangle]
pub extern "system" fn Java_io_ppskit_questrunner_core_JniBindings_nativeStop(
    mut env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    to_java_string(&mut env, with_snapshot(QuestRunnerAdapter::stop))
}

#[no_mangle]
pub extern "system" fn Java_io_ppskit_questrunner_core_JniBindings_nativeCreatePairing(
    mut env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    companion_base_url: JString<'_>,
    room: JString<'_>,
) -> jstring {
    let companion_base_url = java_string(&mut env, companion_base_url);
    let room = java_string(&mut env, room);
    let payload = with_runner(|runner| runner.create_pairing_json(&companion_base_url, &room));
    to_java_string(&mut env, payload)
}

#[no_mangle]
pub extern "system" fn Java_io_ppskit_questrunner_core_JniBindings_nativeBeginRelay(
    mut env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    secret: JString<'_>,
) -> jstring {
    let secret = java_string(&mut env, secret);
    let payload = with_runner(|runner| runner.begin_relay_json(&secret));
    to_java_string(&mut env, payload)
}

#[no_mangle]
pub extern "system" fn Java_io_ppskit_questrunner_core_JniBindings_nativeHandleRelayFrame(
    mut env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    frame: JString<'_>,
) -> jstring {
    let frame = java_string(&mut env, frame);
    let payload = with_runner(|runner| runner.handle_relay_json(&frame));
    to_java_string(&mut env, payload)
}

#[no_mangle]
pub extern "system" fn Java_io_ppskit_questrunner_core_JniBindings_nativePollRelay(
    mut env: JNIEnv<'_>,
    _receiver: JObject<'_>,
) -> jstring {
    let payload = with_runner(QuestRunnerAdapter::poll_relay_json);
    to_java_string(&mut env, payload)
}

#[no_mangle]
pub extern "system" fn Java_io_ppskit_questrunner_core_JniBindings_nativeEndRelay(
    mut env: JNIEnv<'_>,
    _receiver: JObject<'_>,
    reason: JString<'_>,
) -> jstring {
    let reason = java_string(&mut env, reason);
    let payload = with_runner(|runner| runner.end_relay_json(&reason));
    to_java_string(&mut env, payload)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_target_is_prepared_but_not_locally_armed() {
        let runner = QuestRunnerAdapter::default();
        assert!(!runner.core.snapshot().safety.local_armed);
        assert!(runner.snapshot_json().contains("\"armed\":false"));
    }

    #[test]
    fn starting_requires_a_separate_local_arm_action() {
        let mut runner = QuestRunnerAdapter::default();
        let prepared_revision = runner.core.revision();
        runner.start_demo();
        assert_eq!(runner.core.revision(), prepared_revision);
        assert!(runner.message.contains("armed locally"));

        runner.arm();
        runner.start_demo();
        assert_eq!(runner.core.snapshot().run.phase, RunnerPhase::Running);
    }

    #[test]
    fn pairing_is_created_by_the_rust_authority() {
        let mut runner = QuestRunnerAdapter::default();
        let response: Value = serde_json::from_str(
            &runner.create_pairing_json("https://lab.example/companion/", "quest_lab_01"),
        )
        .unwrap();
        assert_eq!(response["ok"], true);
        assert_eq!(response["secret"].as_str().unwrap().len(), 43);
        assert!(response["invitation"]
            .as_str()
            .unwrap()
            .contains("session_id="));
    }
}
