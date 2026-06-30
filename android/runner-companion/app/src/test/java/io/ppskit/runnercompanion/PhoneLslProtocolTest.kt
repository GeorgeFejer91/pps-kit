package io.ppskit.runnercompanion

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PhoneLslProtocolTest {
    @Test
    fun commandAndAckSamplesUsePcRunnerFieldOrder() {
        val signal = PhoneLslCommandSignal(
            commandId = "cmd-1",
            sessionId = "session-001",
            senderId = "controller-phone",
            command = "start_experiment",
            issuedLslTime = 10.0,
            payload = JSONObject().put("token", "secret"),
        )

        val parsedSignal = phoneCommandFromSample(phoneCommandToSample(signal))

        assertEquals(PHONE_LSL_COMMAND_SCHEMA, phoneCommandToSample(signal)[0])
        assertEquals("cmd-1", parsedSignal.commandId)
        assertEquals("start_experiment", parsedSignal.command)
        assertEquals("secret", parsedSignal.payload.getString("token"))

        val ack = PhoneLslCommandAck(
            commandId = parsedSignal.commandId,
            sessionId = parsedSignal.sessionId,
            receiverId = "android_phone",
            status = "applied",
            reason = "",
            receivedLslTime = 10.1,
            appliedLslTime = 10.2,
            ackLslTime = 10.3,
            payload = JSONObject().put("state_changed", true),
        )

        val parsedAck = phoneAckFromSample(phoneAckToSample(ack))

        assertEquals(PHONE_LSL_ACK_SCHEMA, phoneAckToSample(ack)[0])
        assertEquals("cmd-1", parsedAck.commandId)
        assertEquals("applied", parsedAck.status)
        assertTrue(parsedAck.payload.getBoolean("state_changed"))
    }

    @Test
    fun tokenGateRejectsInvalidCommandBeforeHandlerRuns() {
        val runPackage = packageWithLslCommands()
        var handlerRan = false
        val badTokenSignal = PhoneLslCommandSignal(
            commandId = "cmd-2",
            sessionId = "session-001",
            senderId = "pc-runner",
            command = "pause",
            issuedLslTime = 11.0,
            payload = JSONObject().put("token", "wrong"),
        )

        val ack = phoneCommandAckForSignal(
            signal = badTokenSignal,
            runPackage = runPackage,
            expectedToken = "secret",
        ) {
            handlerRan = true
            PhoneLslCommandApplicationResult()
        }

        assertEquals("rejected", ack.status)
        assertEquals("invalid_token", ack.reason)
        assertFalse(handlerRan)
    }

    @Test
    fun validCommandProducesAppliedAckAfterHandlerPayload() {
        val runPackage = packageWithLslCommands()
        val signal = PhoneLslCommandSignal(
            commandId = "cmd-3",
            sessionId = "session-001",
            senderId = "controller-phone",
            command = "pause",
            issuedLslTime = 12.0,
            payload = JSONObject()
                .put("companion_token", "secret")
                .put("package_id", "pkg-001")
                .put("participant_id", "P001")
                .put("target_session_id", "part-001")
                .put("target_part_session_id", "part-001")
                .put("target_session_group_id", "group-001")
                .put("target_part_number", "1")
                .put("requested_by", "android_controller"),
        )

        val ack = phoneCommandAckForSignal(
            signal = signal,
            runPackage = runPackage,
            expectedToken = "secret",
            receivedLslTime = 12.1,
            appliedLslTime = 12.2,
            ackLslTime = 12.3,
        ) { received ->
            PhoneLslCommandApplicationResult(
                status = "applied",
                payload = JSONObject().put("command", received.command).put("state_changed", true),
            )
        }

        assertEquals("applied", ack.status)
        assertEquals(12.2, ack.appliedLslTime, 0.0001)
        assertEquals("pause", ack.payload.getString("command"))
        assertTrue(ack.payload.getBoolean("state_changed"))
        assertEquals("pkg-001", ack.payload.getString("package_id"))
        assertEquals("P001", ack.payload.getString("participant_id"))
        assertEquals("part-001", ack.payload.getString("target_session_id"))
        assertEquals("part-001", ack.payload.getString("target_part_session_id"))
        assertEquals("group-001", ack.payload.getString("target_session_group_id"))
        assertEquals("1", ack.payload.getString("target_part_number"))
        assertEquals("android_controller", ack.payload.getString("requested_by"))
        assertFalse(ack.payload.has("companion_token"))
        assertFalse(ack.payload.has("token"))
    }

    @Test
    fun commandAckRejectsExplicitPackageOrPartIdentityDrift() {
        val runPackage = packageWithLslCommands()
        val badPackageSignal = PhoneLslCommandSignal(
            commandId = "cmd-package-drift",
            sessionId = "part-001",
            senderId = "controller-phone",
            command = "pause",
            issuedLslTime = 12.0,
            payload = JSONObject()
                .put("token", "secret")
                .put("package_id", "wrong-package")
                .put("target_part_session_id", "part-001"),
        )
        val badPartSignal = PhoneLslCommandSignal(
            commandId = "cmd-part-drift",
            sessionId = "part-001",
            senderId = "controller-phone",
            command = "pause",
            issuedLslTime = 12.0,
            payload = JSONObject()
                .put("token", "secret")
                .put("package_id", "pkg-001")
                .put("target_part_session_id", "wrong-part"),
        )

        val packageAck = phoneCommandAckForSignal(
            signal = badPackageSignal,
            runPackage = runPackage,
            expectedToken = "secret",
        ) { PhoneLslCommandApplicationResult(status = "applied") }
        val partAck = phoneCommandAckForSignal(
            signal = badPartSignal,
            runPackage = runPackage,
            expectedToken = "secret",
        ) { PhoneLslCommandApplicationResult(status = "applied") }

        assertEquals("rejected", packageAck.status)
        assertEquals("package_mismatch", packageAck.reason)
        assertEquals("rejected", partAck.status)
        assertEquals("part_session_mismatch", partAck.reason)
    }

    @Test
    fun runtimeStatusDocumentsMissingNativeTransportAndPrivacyBoundary() {
        val status = phoneLslRuntimeStatus(
            packageWithLslCommands(),
            runId = "phone-run-001",
            participantMetadata = participantMetadata(),
            hapticCapability = hapticCapability(),
        )

        assertEquals(PHONE_LSL_RUNTIME_STATUS_SCHEMA, status.getString("schema"))
        assertEquals("local_lsl_marker_mirror", status.getString("current_android_source_behavior"))
        assertFalse(status.getBoolean("native_transport_available"))
        assertTrue(status.getString("reason").contains("liblsl_android_class_unavailable"))
        assertEquals("PPSCommandSignalsV1", status.getJSONObject("streams").getString("command_signals"))
        assertFalse(status.getJSONObject("privacy").getBoolean("demographics_in_stream_name"))
        assertEquals("30", status.getJSONObject("participant_metadata_summary").getString("age_years"))
        assertEquals("right", status.getJSONObject("participant_metadata_summary").getString("handedness"))
        assertEquals(20, status.getJSONObject("haptic_capability_summary").getInt("recommended_threshold_percent"))
        assertTrue(status.getJSONObject("command_protocol").getBoolean("token_required"))

        val descriptions = status.getJSONObject("stream_descriptions")
        assertEquals("pps-android-lsl-stream-descriptions.v1", descriptions.getString("schema"))
        assertFalse(descriptions.getJSONObject("privacy").getBoolean("demographics_in_stream_name"))

        val richMarkers = descriptions.getJSONObject("rich_markers")
        assertEquals("PPSMarkersV2", richMarkers.getString("name"))
        assertEquals("Markers", richMarkers.getString("type"))
        assertEquals("outlet", richMarkers.getString("role"))
        assertEquals("string", richMarkers.getString("channel_format"))
        assertEquals(PHONE_LSL_MARKER_CHANNELS.size, richMarkers.getInt("channel_count"))
        assertEquals(
            "payload_json",
            richMarkers.getJSONArray("channel_labels").getString(PHONE_LSL_MARKER_CHANNELS.size - 1),
        )
        assertEquals("phone-run-001", richMarkers.getString("run_id"))
        val richSessionMetadata = JSONObject(richMarkers.getString("session_metadata_json"))
        assertEquals("pkg-001", richSessionMetadata.getString("package_id"))
        assertEquals("seed-123", richSessionMetadata.getString("randomization_seed"))
        assertEquals(2, richSessionMetadata.getInt("participant_roster_count"))
        assertEquals(
            "segment5hash",
            richSessionMetadata.getJSONObject("source_segment_hashes").getString("source_segment5_manifest_sha256"),
        )
        assertFalse(richSessionMetadata.getBoolean("demographics_in_stream_name"))
        val participantSummary = richSessionMetadata.getJSONObject("participant_metadata_summary")
        assertEquals("pps-android-lsl-participant-metadata-summary.v1", participantSummary.getString("schema"))
        assertEquals("P001", participantSummary.getString("participant_id"))
        assertEquals("30", participantSummary.getString("age_years"))
        assertEquals("right", participantSummary.getString("handedness"))
        assertEquals("prefer_not_to_say", participantSummary.getString("gender"))
        assertEquals("20", participantSummary.getString("tactile_threshold_percent"))
        assertEquals("android_haptic_calibration", participantSummary.getString("tactile_threshold_source"))
        assertEquals("metadata_payload_only", participantSummary.getString("stream_privacy"))
        val hapticSummary = richSessionMetadata.getJSONObject("haptic_capability_summary")
        assertEquals("pps-android-lsl-haptic-capability-summary.v1", hapticSummary.getString("schema"))
        assertTrue(hapticSummary.getBoolean("has_vibrator"))
        assertTrue(hapticSummary.getBoolean("has_amplitude_control"))
        assertEquals("amplitude_percent_supported", hapticSummary.getString("calibration_policy"))
        assertEquals(20, hapticSummary.getInt("recommended_threshold_percent"))
        assertEquals(51, hapticSummary.getInt("recommended_amplitude"))

        val numericTriggers = descriptions.getJSONObject("numeric_triggers")
        assertEquals("PPSTriggerCodes", numericTriggers.getString("name"))
        assertEquals("int32", numericTriggers.getString("channel_format"))
        assertEquals("event_code", numericTriggers.getJSONArray("channel_labels").getString(0))
        assertEquals(richMarkers.getString("session_metadata_json"), numericTriggers.getString("session_metadata_json"))

        val commandSignals = descriptions.getJSONObject("command_signals")
        assertEquals("inlet", commandSignals.getString("role"))
        assertEquals(PHONE_LSL_COMMAND_CHANNELS.size, commandSignals.getInt("channel_count"))
        assertTrue(commandSignals.getBoolean("token_required"))
    }

    @Test
    fun runtimeStatusSeparatesNativeMarkerAndCommandTransportState() {
        val bridge = PhoneNativeLslBridgeStatus(
            available = true,
            enabled = false,
            backend = "liblsl-android-reflection",
        )
        val marker = bridge.copy(enabled = true)
        val command = bridge.copy(enabled = true)

        val status = phoneLslRuntimeStatus(
            runPackage = packageWithLslCommands(),
            runId = "phone-run-002",
            nativeBridgeStatus = bridge,
            markerTransportStatus = marker,
            commandTransportStatus = command,
        )

        assertTrue(status.getBoolean("native_transport_available"))
        assertTrue(status.getBoolean("native_marker_transport_enabled"))
        assertTrue(status.getBoolean("command_receiver_available"))
        assertEquals("native_lsl_markers_and_commands_with_local_mirror", status.getString("current_android_source_behavior"))
        assertTrue(status.getJSONObject("native_bridge").getJSONObject("command_transport").getBoolean("enabled"))
        assertTrue(
            status.getJSONObject("stream_descriptions")
                .getJSONObject("command_acks")
                .getString("source_id")
                .startsWith("pps-android-command-acks-v1-phone-run-002"),
        )
    }

    @Test
    fun defaultCommandContractIncludesStopAfterBlock() {
        val runPackage = packageWithDefaultLslCommands()
        val status = phoneLslRuntimeStatus(runPackage, runId = "phone-run-003")
        val commands = status.getJSONObject("command_protocol").getJSONArray("supported_commands")
        val commandNames = (0 until commands.length()).map { commands.getString(it) }

        assertTrue(commandNames.contains("stop_after_block"))

        val signal = PhoneLslCommandSignal(
            commandId = "cmd-stop-1",
            sessionId = "part-001",
            senderId = "pc-runner",
            command = "stop_after_block",
            issuedLslTime = 13.0,
            payload = JSONObject().put("token", "secret"),
        )
        var handlerCommand = ""

        val ack = phoneCommandAckForSignal(
            signal = signal,
            runPackage = runPackage,
            expectedToken = "secret",
        ) { received ->
            handlerCommand = received.command
            PhoneLslCommandApplicationResult(
                status = "applied",
                reason = "will_stop_after_current_block",
                payload = JSONObject().put("stop_after_block_requested", true),
            )
        }

        assertEquals("stop_after_block", handlerCommand)
        assertEquals("applied", ack.status)
        assertEquals("will_stop_after_current_block", ack.reason)
        assertTrue(ack.payload.getBoolean("stop_after_block_requested"))
    }

    private fun packageWithLslCommands(): MobileRunPackage =
        MobilePackageParser.parseManifest(
            """
            {
              "schema": "$MOBILE_PACKAGE_SCHEMA",
              "package_id": "pkg-001",
              "participant_id": "P001",
              "session_id": "session-001",
              "session_group_id": "group-001",
              "part_session_id": "part-001",
              "part_number": "1",
              "participant_roster": ["P001", "P002"],
              "randomization_seed": "seed-123",
              "source_segment_hashes": {
                "schema": "pps-mobile-source-segment-hashes.v1",
                "source_run_setup_manifest_sha256": "runhash",
                "source_segment5_manifest_sha256": "segment5hash",
                "segment6_order_csv_sha256": "orderhash",
                "segment5_block_csvs": [
                  {"block_id": "block-01", "sha256": "blockhash"}
                ]
              },
              "mobile_runnable": true,
              "phone_owned_session": true,
              "reconstruction": {
                "schema": "pps-mobile-reconstruction-contract.v2",
                "package_asset_strategy": "trial_building_blocks_only",
                "schedule_hash": "schedulehash"
              },
              "lsl": {
                "schema": "pps-mobile-lsl-contract.v1",
                "runtime_authority": "android_phone",
                "privacy_default": "metadata_payload_only",
                "stream_names": {
                  "rich_markers": "PPSMarkersV2",
                  "numeric_triggers": "PPSTriggerCodes",
                  "command_signals": "PPSCommandSignalsV1",
                  "command_acks": "PPSCommandAcksV1"
                },
                "native_android_lsl_required": true,
                "current_android_source_behavior": "local_lsl_marker_mirror",
                "supported_commands": ["start_experiment", "pause"]
              },
              "assets": [],
              "blocks": [],
              "building_blocks": [],
              "warnings": []
            }
            """.trimIndent(),
        )

    private fun packageWithDefaultLslCommands(): MobileRunPackage =
        MobilePackageParser.parseManifest(
            """
            {
              "schema": "$MOBILE_PACKAGE_SCHEMA",
              "package_id": "pkg-001",
              "participant_id": "P001",
              "session_id": "session-001",
              "session_group_id": "group-001",
              "part_session_id": "part-001",
              "part_number": "1",
              "mobile_runnable": true,
              "phone_owned_session": true,
              "lsl": {
                "schema": "pps-mobile-lsl-contract.v1",
                "runtime_authority": "android_phone",
                "privacy_default": "metadata_payload_only",
                "stream_names": {
                  "rich_markers": "PPSMarkersV2",
                  "numeric_triggers": "PPSTriggerCodes",
                  "command_signals": "PPSCommandSignalsV1",
                  "command_acks": "PPSCommandAcksV1"
                },
                "native_android_lsl_required": true,
                "current_android_source_behavior": "local_lsl_marker_mirror"
              },
              "assets": [],
              "blocks": [],
              "building_blocks": [],
              "warnings": []
            }
            """.trimIndent(),
        )

    private fun participantMetadata(): JSONObject =
        JSONObject()
            .put("schema", "pps-android-phone-participant-metadata.v1")
            .put("participant_id", "P001")
            .put("session_id", "session-001")
            .put("session_group_id", "group-001")
            .put("part_session_id", "part-001")
            .put("part_number", "1")
            .put("age_years", "30")
            .put("handedness", "right")
            .put("gender", "prefer_not_to_say")
            .put("tactile_threshold_percent", "20")
            .put("tactile_threshold_source", "android_haptic_calibration")
            .put("tactile_threshold_calibration_status", "threshold_detected")
            .put("stream_privacy", "metadata_payload_only")

    private fun hapticCapability(): JSONObject =
        JSONObject()
            .put("schema", "pps-android-haptic-capability.v1")
            .put("has_vibrator", true)
            .put("has_amplitude_control", true)
            .put("calibration_policy", "amplitude_percent_supported")
            .put("calibration_status", "threshold_detected")
            .put("recommended_threshold_percent", 20)
            .put("recommended_amplitude", 51)
}
