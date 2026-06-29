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
            payload = JSONObject().put("companion_token", "secret"),
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
    }

    @Test
    fun runtimeStatusDocumentsMissingNativeTransportAndPrivacyBoundary() {
        val status = phoneLslRuntimeStatus(packageWithLslCommands(), runId = "phone-run-001")

        assertEquals(PHONE_LSL_RUNTIME_STATUS_SCHEMA, status.getString("schema"))
        assertEquals("local_lsl_marker_mirror", status.getString("current_android_source_behavior"))
        assertFalse(status.getBoolean("native_transport_available"))
        assertTrue(status.getString("reason").contains("liblsl_android_class_unavailable"))
        assertEquals("PPSCommandSignalsV1", status.getJSONObject("streams").getString("command_signals"))
        assertFalse(status.getJSONObject("privacy").getBoolean("demographics_in_stream_name"))
        assertTrue(status.getJSONObject("command_protocol").getBoolean("token_required"))
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
}
