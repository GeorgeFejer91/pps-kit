from __future__ import annotations

from pathlib import Path


ANDROID_SOURCE = (
    Path(__file__).resolve().parents[1]
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

    for source in [main_activity, lsl_protocol, native_bridge, catalog]:
        assert "mobilePackageAssetStrategy(runPackage)" in source

    assert '.put("asset_strategy", mobilePackageAssetStrategy(runPackage))' in main_activity
    assert '.put("package_asset_strategy", runPackage.reconstruction.packageAssetStrategy)' in main_activity
    assert '.put("asset_strategy", mobilePackageAssetStrategy(runPackage))' in lsl_protocol
    assert '.put("asset_strategy", mobilePackageAssetStrategy(runPackage))' in native_bridge
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


def test_android_lsl_runtime_status_exports_stream_descriptions() -> None:
    lsl_protocol = _source("PhoneLslProtocol.kt")

    assert "phoneLslStreamDescriptions" in lsl_protocol
    assert '.put("stream_descriptions", phoneLslStreamDescriptions(runPackage, runId))' in lsl_protocol
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
    assert '.put("demographics_in_stream_name", false)' in lsl_protocol


def test_android_controller_runtime_status_exports_stream_descriptions() -> None:
    controller_commands = _source("PhoneControllerCommands.kt")

    assert "phoneControllerLslStreamDescriptions" in controller_commands
    assert '.put("stream_descriptions", phoneControllerLslStreamDescriptions(pairing, runPackage, summary))' in controller_commands
    assert '"pps-android-lsl-stream-descriptions.v1"' in controller_commands
    assert '"android_controller"' in controller_commands
    assert "PHONE_LSL_COMMAND_STREAM_NAME" in controller_commands
    assert "PHONE_LSL_ACK_STREAM_NAME" in controller_commands
    assert '"outlet"' in controller_commands
    assert '"inlet"' in controller_commands
    assert '"pps-android-controller-signals-v1-$sessionToken-$controllerToken"' in controller_commands
    assert '"pps-*-command-acks-v1-*"' in controller_commands
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
    assert '.put("audio_timing_strategy", "audiotrack_pcm_wav_playback_head")' in main_activity
    assert '.put("audio_scheduler", "audiotrack_playback_head")' in main_activity
    assert "MediaPlayer" not in all_sources


def test_android_companion_discovery_preserves_local_hotspot_privacy_contract() -> None:
    discovery = _source("CompanionDiscovery.kt")

    assert 'COMPANION_DISCOVERY_NETWORK_SCOPE = "same_lan_or_local_hotspot"' in discovery
    assert 'COMPANION_DISCOVERY_TOKEN_DELIVERY = "qr_or_manual_uri_only"' in discovery
    assert 'setOf("lan", "phone_hotspot", "wifi_direct")' in discovery
    assert 'optBoolean("also_sent_as_limited_broadcast", false)' in discovery
    assert 'optInt("ttl", 0) == 1' in discovery
    assert 'optBoolean("contains_pairing_token", true)' in discovery
    assert 'optBoolean("contains_participant_demographics", true)' in discovery
    assert 'optBoolean("stream_names_are_generic", false)' in discovery
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


def test_android_phone_run_command_diary_separates_local_ui_runtime_and_native_sources() -> None:
    main_activity = _source("MainActivity.kt")

    assert 'commandSource: String = "phone_runtime"' in main_activity
    assert '.put("command_source", commandSource)' in main_activity
    assert '.put("sender_id", senderId)' in main_activity
    assert 'commandSource = "phone_ui"' in main_activity
    assert 'senderId = "android_phone_ui"' in main_activity
    assert 'startCommandAction = "start_phone_run"' in main_activity
    assert 'startCommandAction = "start_full_experiment_part"' in main_activity
    assert '.put("command_source", "native_lsl")' in main_activity


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
