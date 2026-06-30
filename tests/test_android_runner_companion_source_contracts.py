from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ANDROID_SOURCE = (
    REPO_ROOT
    / "android"
    / "runner-companion"
    / "app"
    / "src"
    / "main"
    / "java"
    / "io"
    / "ppskit"
    / "runnercompanion"
)


def _source(name: str) -> str:
    return (ANDROID_SOURCE / name).read_text(encoding="utf-8")


def _load_python_script(relative_path: str):
    path = REPO_ROOT / relative_path
    module_name = path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_android_phone_runtime_preserves_mobile_package_asset_strategy() -> None:
    models = _source("MobileRuntimeModels.kt")
    main_activity = _source("MainActivity.kt")
    lsl_protocol = _source("PhoneLslProtocol.kt")
    native_bridge = _source("PhoneNativeLslBridge.kt")
    catalog = _source("PhoneRunCatalog.kt")

    assert "val assetStrategy: String" in models
    assert "val packageAssetStrategy: String" in models
    assert 'root.optString("asset_strategy"' in models
    assert 'optString("package_asset_strategy", "")' in models

    for source in [main_activity, lsl_protocol, catalog]:
        assert "mobilePackageAssetStrategy(runPackage)" in source
    assert "phoneLslSessionMetadataJson(runPackage" in native_bridge

    assert '.put("asset_strategy", mobilePackageAssetStrategy(runPackage))' in main_activity
    assert '.put("package_asset_strategy", runPackage.reconstruction.packageAssetStrategy)' in main_activity
    assert '.put("asset_strategy", mobilePackageAssetStrategy(runPackage))' in lsl_protocol
    assert '.put("asset_strategy", mobilePackageAssetStrategy(runPackage))' in catalog
    assert '.put("package_asset_strategy", runPackage.reconstruction.packageAssetStrategy)' in catalog


def test_android_phone_runtime_preserves_reconstruction_hierarchy_in_artifacts() -> None:
    models = _source("MobileRuntimeModels.kt")
    main_activity = _source("MainActivity.kt")

    assert "val studyHierarchy: List<String>" in models
    assert "val sourceRunSetupManifestPath: String" in models
    assert 'studyHierarchy = optJSONArray("study_hierarchy").toStringList()' in models
    assert 'sourceRunSetupManifestPath = optString("source_run_setup_manifest_path", "")' in models
    assert '.put("study_hierarchy", jsonStringArray(runPackage.reconstruction.studyHierarchy))' in main_activity
    assert '.put("source_run_setup_manifest_path", runPackage.reconstruction.sourceRunSetupManifestPath)' in main_activity


def test_android_phone_session_metadata_preserves_source_provenance() -> None:
    models = _source("MobileRuntimeModels.kt")
    main_activity = _source("MainActivity.kt")
    native_bridge = _source("PhoneNativeLslBridge.kt")
    catalog = _source("PhoneRunCatalog.kt")

    assert "val participantRoster: List<String>" in models
    assert "val randomizationSeed: String" in models
    assert "data class MobileSourceSegmentHashes" in models
    assert 'participantRoster = root.optJSONArray("participant_roster").toStringList()' in models
    assert 'randomizationSeed = root.optString("randomization_seed", "")' in models
    assert 'sourceSegmentHashes = root.optJSONObject("source_segment_hashes").toMobileSourceSegmentHashes()' in models

    for source in [main_activity, catalog]:
        assert '.put("participant_roster_count", runPackage.participantRoster.size)' in source
        assert '.put("randomization_seed", runPackage.randomizationSeed)' in source
        assert '.put("source_segment_hashes", runPackage.sourceSegmentHashes.toJsonObject())' in source

    assert "phoneLslSessionMetadataJson(runPackage" in native_bridge


def test_android_lsl_runtime_status_exports_stream_descriptions() -> None:
    lsl_protocol = _source("PhoneLslProtocol.kt")

    assert "phoneLslStreamDescriptions" in lsl_protocol
    assert 'phoneLslStreamDescriptions(runPackage, runId, participantMetadata, hapticCapability)' in lsl_protocol
    assert "phoneLslSessionMetadataJson" in lsl_protocol
    assert '.put("session_metadata_json", sessionMetadataJson)' in lsl_protocol
    assert "phoneParticipantMetadataSummary" in lsl_protocol
    assert "phoneHapticCapabilitySummary" in lsl_protocol
    assert '"pps-android-lsl-participant-metadata-summary.v1"' in lsl_protocol
    assert '"pps-android-lsl-haptic-capability-summary.v1"' in lsl_protocol
    assert '"pps-android-lsl-stream-descriptions.v1"' in lsl_protocol
    assert '"PPSMarkersV2"' in lsl_protocol
    assert '"PPSTriggerCodes"' in lsl_protocol
    assert '"PPSCommandSignalsV1"' in lsl_protocol
    assert '"PPSCommandAcksV1"' in lsl_protocol
    assert '"pps-android-markers-v2-$runToken"' in lsl_protocol
    assert '"pps-android-trigger-codes-$runToken"' in lsl_protocol
    assert '"pps-android-command-acks-v1-$runToken"' in lsl_protocol
    assert '"pps-*-command-signals-v1-*"' in lsl_protocol
    assert '.put("channel_labels", stringArray(PHONE_LSL_MARKER_CHANNELS))' in lsl_protocol
    assert '.put("channel_labels", stringArray(PHONE_LSL_COMMAND_CHANNELS))' in lsl_protocol
    assert '.put("channel_labels", stringArray(PHONE_LSL_ACK_CHANNELS))' in lsl_protocol
    assert '.put("participant_roster_count", runPackage.participantRoster.size)' in lsl_protocol
    assert '.put("randomization_seed", runPackage.randomizationSeed)' in lsl_protocol
    assert '.put("source_segment_hashes", runPackage.sourceSegmentHashes.toJsonObject())' in lsl_protocol
    assert '.put("demographics_in_stream_name", false)' in lsl_protocol


def test_android_native_lsl_bridge_resolves_multiple_command_and_ack_streams() -> None:
    native_bridge = _source("PhoneNativeLslBridge.kt")

    assert "PHONE_NATIVE_LSL_MAX_COMMAND_STREAMS = 8" in native_bridge
    assert "fun resolveStreams(name: String, maximum: Int, timeoutS: Double): List<Any>" in native_bridge
    assert "resolveStreams(" in native_bridge
    assert "maximum = PHONE_NATIVE_LSL_MAX_COMMAND_STREAMS" in native_bridge
    assert "commandInlets = commandInlets" in native_bridge
    assert "private val commandInlets: List<Any>" in native_bridge
    assert "for ((index, inlet) in commandInlets.withIndex())" in native_bridge
    assert "if (index == 0) timeoutS else 0.0" in native_bridge
    assert "private var ackInlets: List<Any> = emptyList()" in native_bridge
    assert "for ((index, inlet) in ackInlets.withIndex())" in native_bridge
    assert ".put(\"max_command_streams_resolved\", PHONE_NATIVE_LSL_MAX_COMMAND_STREAMS)" in native_bridge


def test_android_command_acks_echo_nonsecret_target_identity() -> None:
    lsl_protocol = _source("PhoneLslProtocol.kt")

    assert "PHONE_COMMAND_ACK_ECHO_PAYLOAD_FIELDS" in lsl_protocol
    for field in [
        "package_id",
        "participant_id",
        "target_session_id",
        "target_part_session_id",
        "target_session_group_id",
        "target_part_number",
        "requested_by",
    ]:
        assert f'"{field}"' in lsl_protocol
    echo_allow_list = lsl_protocol.split("PHONE_COMMAND_ACK_ECHO_PAYLOAD_FIELDS", maxsplit=1)[1].split(")", maxsplit=1)[0]
    assert '"token"' not in echo_allow_list
    assert '"companion_token"' not in echo_allow_list
    assert "private fun phoneCommandAckPayload" in lsl_protocol
    assert "phoneCommandAckPayload(signal, result.payload)" in lsl_protocol
    assert 'return "package_mismatch"' in lsl_protocol
    assert 'return "part_session_mismatch"' in lsl_protocol


def test_android_controller_runtime_status_exports_stream_descriptions() -> None:
    models = _source("MobileRuntimeModels.kt")
    controller_commands = _source("PhoneControllerCommands.kt")
    main_activity = _source("MainActivity.kt")

    assert "data class MobilePackageSummary" in models
    assert "val sessionGroupId: String" in models
    assert "val partSessionId: String" in models
    assert "val partNumber: String" in models
    assert 'sessionGroupId = item.optString("session_group_id", "")' in models
    assert 'partSessionId = item.optString("part_session_id", "")' in models
    assert 'partNumber = item.optString("part_number", "")' in models
    assert "phoneControllerLslStreamDescriptions" in controller_commands
    assert "private fun resolvePhoneControllerTarget" in controller_commands
    assert "summary.partSessionId.ifBlank { summary.sessionId }" in controller_commands
    assert '.put("stream_descriptions", phoneControllerLslStreamDescriptions(pairing, runPackage, summary))' in controller_commands
    assert '.put("target_session_id", target.sessionId)' in controller_commands
    assert "selectedSummary?.partSessionId" in main_activity
    assert '"pps-android-lsl-stream-descriptions.v1"' in controller_commands
    assert '"android_controller"' in controller_commands
    assert "PHONE_LSL_COMMAND_STREAM_NAME" in controller_commands
    assert "PHONE_LSL_ACK_STREAM_NAME" in controller_commands
    assert '"outlet"' in controller_commands
    assert '"inlet"' in controller_commands
    assert '"pps-android-controller-signals-v1-$sessionToken-$controllerToken"' in controller_commands
    assert '"pps-*-command-acks-v1-*"' in controller_commands
    assert '"stop_after_block"' in controller_commands
    assert '"stop_after_block" to "Stop After Block"' in main_activity
    assert '"operator_note"' in controller_commands
    assert '"operator_note"' in main_activity
    assert '"Operator note"' in main_activity
    assert "commandPayload: JSONObject" in controller_commands
    assert 'JSONObject().put("note", note)' in main_activity
    assert '.put("channel_labels", stringArray(PHONE_LSL_COMMAND_CHANNELS))' in controller_commands
    assert '.put("channel_labels", stringArray(PHONE_LSL_ACK_CHANNELS))' in controller_commands
    assert '.put("demographics_in_stream_name", false)' in controller_commands


def test_android_phone_runtime_uses_audiotrack_timing_not_mediaplayer() -> None:
    playback = _source("PhoneAudioPlayback.kt")
    main_activity = _source("MainActivity.kt")
    all_sources = "\n".join(path.read_text(encoding="utf-8") for path in ANDROID_SOURCE.glob("*.kt"))

    assert "import android.media.AudioTrack" in playback
    assert "internal suspend fun playBlockAudioWithAudioTrack" in playback
    assert "playbackHeadPosition" in playback
    assert "PhoneAudioCueDelivery" in playback
    assert "PhoneAudioPlaybackStart" in playback
    assert "onPlaybackStart(" in playback
    assert '.put("audio_timing_strategy", "audiotrack_pcm_wav_playback_head")' in main_activity
    assert "fun addAudioPlaybackStart" in main_activity
    assert '"audio_playback_start"' in main_activity
    assert '.put("audio_playback_start_state", start.playStateLabel)' in main_activity
    assert '.put("audio_track_buffer_size_frames", start.bufferSizeFrames)' in main_activity
    assert '.put("audio_scheduler", "audiotrack_playback_head")' in main_activity
    assert '"audio_playback_start" -> 12' in main_activity
    assert "MediaPlayer" not in all_sources


def test_android_companion_discovery_preserves_local_hotspot_privacy_contract() -> None:
    discovery = _source("CompanionDiscovery.kt")

    assert 'COMPANION_DISCOVERY_NETWORK_SCOPE = "same_lan_or_local_hotspot"' in discovery
    assert 'COMPANION_DISCOVERY_TOKEN_DELIVERY = "qr_or_manual_uri_only"' in discovery
    assert 'setOf("lan", "phone_hotspot", "wifi_direct")' in discovery
    assert 'optBoolean("also_sent_as_limited_broadcast", false)' in discovery
    assert 'COMPANION_DISCOVERY_LIMITED_BROADCAST_TARGET = "255.255.255.255"' in discovery
    assert 'COMPANION_DISCOVERY_DIRECTED_BROADCAST_TARGET = "interface_ipv4_directed_broadcasts"' in discovery
    assert 'optJSONArray("broadcast_targets")' in discovery
    assert 'optInt("ttl", 0) == 1' in discovery
    assert 'optBoolean("contains_pairing_token", true)' in discovery
    assert 'optBoolean("contains_participant_demographics", true)' in discovery
    assert 'optBoolean("stream_names_are_generic", false)' in discovery
    assert "assertNoDiscoveryPrivacyLeakage(root)" in discovery
    assert "companionDiscoveryTokenFields" in discovery
    assert "companionDiscoveryParticipantFields" in discovery
    assert "companionDiscoveryStreamFields" in discovery
    assert "createMulticastLock" in discovery
    assert "MulticastSocket(null)" in discovery


def test_android_phone_run_zip_exports_catalog_snapshot() -> None:
    main_activity = _source("MainActivity.kt")

    assert "addPhoneRunCatalogSnapshot(output, context.filesDir)" in main_activity
    assert "addPhoneOwnedExportsSnapshot(output, context.filesDir)" in main_activity
    assert 'File(filesDir, "phone_run_catalog")' in main_activity
    assert 'addZipEntries(output, catalogRoot, "phone_run_catalog")' in main_activity
    assert 'File(filesDir, "phone_owned_exports")' in main_activity
    assert 'addZipEntries(output, exportRoot, "phone_owned_exports")' in main_activity


def test_android_phone_run_writes_plain_event_diary() -> None:
    main_activity = _source("MainActivity.kt")

    assert 'writePhoneEventsCsv(File(dir, "events.csv"), events)' in main_activity
    assert 'writePhoneEventsCsv(File(dir, "lsl_marker_mirror.csv"), lslMarkers)' in main_activity
    assert 'writePhoneTriggerCodesCsv(File(dir, "trigger_codes.csv"), lslMarkers)' in main_activity
    assert "private fun writePhoneTriggerCodesCsv" in main_activity
    assert '.put("lsl_marker_mirror_count", lslMarkers.size)' in main_activity
    assert '.put("native_lsl_pushed_count", nativeLslPushedCount)' in main_activity
    assert '.put("native_lsl_failed_count", nativeLslFailedCount)' in main_activity
    assert '.put("native_lsl_command_received_count", nativeLslCommandReceivedCount)' in main_activity
    assert '.put("native_lsl_command_ack_count", nativeLslCommandAckCount)' in main_activity
    assert '.put("native_lsl_command_ack_failed_count", nativeLslCommandAckFailedCount)' in main_activity
    assert '.put("native_lsl_command_rejected_count", nativeLslCommandRejectedCount)' in main_activity
    assert '.put("command_diary_count", commandDiary.size)' in main_activity


def test_android_phone_run_writes_artifact_file_inventory() -> None:
    main_activity = _source("MainActivity.kt")

    assert 'PHONE_RUN_ARTIFACT_FILE_INVENTORY_SCHEMA = "pps-android-phone-run-artifact-file-inventory.v1"' in main_activity
    assert 'PHONE_RUN_ARTIFACT_FILE_INVENTORY_JSON = "artifact_file_inventory.json"' in main_activity
    assert 'PHONE_RUN_ARTIFACT_FILE_INVENTORY_CSV = "artifact_file_inventory.csv"' in main_activity
    assert "writePhoneRunArtifactFileInventory(" in main_activity
    assert '"artifact_file_inventory_artifact"' in main_activity
    assert '.put("relative_path", phoneRunRelativePath(runDir, file))' in main_activity
    assert '.put("sha256", sha256File(file))' in main_activity


def test_android_phone_run_command_diary_separates_local_ui_runtime_and_native_sources() -> None:
    main_activity = _source("MainActivity.kt")

    assert "private data class PhoneStartCommandEvidence" in main_activity
    assert "startCommandEvidence: PhoneStartCommandEvidence? = null" in main_activity
    assert "startSignal = commandSignal" in main_activity
    assert "PhoneStartCommandEvidence(signal = it, ack = ack, ackSent = ackSent)" in main_activity
    assert "session.recordNativeCommandAckEvidence(" in main_activity
    assert 'commandSource: String = "phone_runtime"' in main_activity
    assert '.put("command_source", commandSource)' in main_activity
    assert '.put("sender_id", senderId)' in main_activity
    assert 'commandSource = "phone_ui"' in main_activity
    assert 'senderId = "android_phone_ui"' in main_activity
    assert 'startCommandAction = "start_phone_run"' in main_activity
    assert 'startCommandAction = "start_full_experiment_part"' in main_activity
    assert '.put("command_source", "native_lsl")' in main_activity


def test_android_runner_mode_local_controls_use_command_diary_path() -> None:
    main_activity = _source("MainActivity.kt")

    assert 'applyRunnerUiCommand("pause", "Pause")' in main_activity
    assert 'applyRunnerUiCommand("resume", "Resume")' in main_activity
    assert 'applyRunnerUiCommand("stop_after_block", "Stop after block")' in main_activity
    assert "fun applyLocalUiCommand(command: String): PhoneLslCommandApplicationResult" in main_activity
    assert '"pause" -> applyPhonePauseLocked(command)' in main_activity
    assert '"resume" -> applyPhoneResumeLocked(command)' in main_activity
    assert '"stop_after_block" -> applyPhoneStopAfterBlockLocked(' in main_activity
    assert 'PhoneLslCommandSignal(' in main_activity
    assert 'senderId = "android_phone_ui"' in main_activity
    assert 'commandSource = "phone_ui"' in main_activity
    assert "commandId = commandId" in main_activity
    assert "fun isPlaybackPaused(): Boolean = playbackGate.isPaused()" in main_activity
    assert "fun hasActiveBlock(): Boolean = activeBlock != null" in main_activity


def test_android_emulator_stress_reports_native_lsl_source_capability() -> None:
    stress = _load_python_script("validation_protocols/scripts/run_android_companion_emulator_ui_stress.py")
    report = stress.android_lsl_capability_assessment()
    source = (REPO_ROOT / "validation_protocols" / "scripts" / "run_android_companion_emulator_ui_stress.py").read_text(
        encoding="utf-8"
    )

    assert report["passed"] is True
    assert report["runner_marker_outlets_supported_by_source"] is True
    assert report["runner_command_receiver_supported_by_source"] is True
    assert report["controller_command_sender_supported_by_source"] is True
    assert report["token_gated_command_ack_supported_by_source"] is True
    assert report["native_lsl_runtime_requires_local_aar"] is True
    assert report["live_validation_state"] in {
        "source_supported_default_build_local_mirror_only",
        "source_supported_aar_present_requires_live_network_validation",
    }
    assert "not_implemented_expected_failure" not in source
    assert '"pause_experiment"' not in source
    assert '"resume_experiment"' not in source
    assert '"stop_after_block"' in source


def test_android_phone_run_writes_phone_owned_min_max_export() -> None:
    main_activity = _source("MainActivity.kt")
    catalog = _source("PhoneRunCatalog.kt")

    assert 'PHONE_OWNED_DATA_EXPORT_SCHEMA = "pps-android-phone-owned-data-export.v1"' in catalog
    assert 'File(filesDir, "phone_owned_exports")' in catalog
    assert 'File(exportRoot, "1.Data_min")' in catalog
    assert 'File(File(File(exportRoot, "2.Data_max"), participantId), "runs/$runId")' in catalog
    assert '"master_successful_participants.csv"' in catalog
    assert '"participant_id",' in catalog
    assert '"reaction_time_ms",' in catalog
    assert "writePhoneOwnedDataExport(" in main_activity
    assert '.put("phone_owned_data_export_path", dataExport?.optString("artifact_path").orEmpty())' in main_activity
