package io.ppskit.runnercompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.json.JSONObject

class PhoneControllerCommandsTest {
    @Test
    fun controllerCommandRowContainsTokenGatedLslCommandSample() {
        val pairing = PairingInfo.parse(
            "pps-companion://pair?host=127.0.0.1&port=8767&session_id=session-001&token=secret&mode=phone_export",
        )
        val row = buildPhoneControllerCommandRow(
            pairing = pairing,
            runPackage = runPackage(),
            summary = null,
            command = "pause",
            commandId = "cmd-controller-1",
            issuedLslTime = 42.0,
            phoneUnixMs = 1000L,
            phoneElapsedRealtimeMs = 2000L,
        )

        assertEquals(PHONE_CONTROLLER_COMMAND_ROW_SCHEMA, row.getString("schema"))
        assertEquals("local_controller_outbox_only", row.getString("current_android_source_behavior"))
        assertFalse(row.getBoolean("native_transport_available"))
        val sample = row.getJSONArray("command_sample")
        assertEquals(PHONE_LSL_COMMAND_SCHEMA, sample.getString(0))
        assertEquals("cmd-controller-1", sample.getString(1))
        assertEquals("part-001", sample.getString(2))
        assertEquals("android_controller", sample.getString(3))
        assertEquals("pause", sample.getString(4))

        val parsed = phoneCommandFromSample((0 until sample.length()).map { sample.getString(it) })
        assertEquals("secret", parsed.payload.getString("token"))
        assertEquals("pkg-001", parsed.payload.getString("package_id"))
        assertEquals("android_elapsed_realtime_not_lsl_local_clock", parsed.payload.getString("timestamp_quality"))
    }

    @Test
    fun controllerCommandRowCanSendStopAfterBlock() {
        val pairing = PairingInfo.parse(
            "pps-companion://pair?host=127.0.0.1&port=8767&session_id=session-001&token=secret&mode=phone_export",
        )
        val row = buildPhoneControllerCommandRow(
            pairing = pairing,
            runPackage = runPackage(),
            summary = null,
            command = "stop_after_block",
            commandId = "cmd-controller-stop-1",
            issuedLslTime = 43.0,
            phoneUnixMs = 1001L,
            phoneElapsedRealtimeMs = 2001L,
        )

        val sample = row.getJSONArray("command_sample")
        assertEquals("stop_after_block", sample.getString(4))
        val parsed = phoneCommandFromSample((0 until sample.length()).map { sample.getString(it) })
        assertEquals("stop_after_block", parsed.command)
        assertEquals("secret", parsed.payload.getString("token"))
    }

    @Test
    fun controllerCommandRowCanSendOperatorNotePayload() {
        val pairing = PairingInfo.parse(
            "pps-companion://pair?host=127.0.0.1&port=8767&session_id=session-001&token=secret&mode=phone_export",
        )
        val row = buildPhoneControllerCommandRow(
            pairing = pairing,
            runPackage = runPackage(),
            summary = null,
            command = "operator_note",
            commandPayload = JSONObject()
                .put("note", "participant asked for a pause")
                .put("token", "wrong-token"),
            commandId = "cmd-controller-note-1",
            issuedLslTime = 44.0,
            phoneUnixMs = 1002L,
            phoneElapsedRealtimeMs = 2002L,
        )

        val sample = row.getJSONArray("command_sample")
        assertEquals("operator_note", sample.getString(4))
        val parsed = phoneCommandFromSample((0 until sample.length()).map { sample.getString(it) })
        assertEquals("operator_note", parsed.command)
        assertEquals("participant asked for a pause", parsed.payload.getString("note"))
        assertEquals("secret", parsed.payload.getString("token"))
        assertEquals("participant asked for a pause", row.getJSONObject("payload").getString("note"))
    }

    @Test
    fun controllerRuntimeStatusDeclaresStrictNativeBoundary() {
        val pairing = PairingInfo.parse(
            "pps-companion://pair?host=127.0.0.1&port=8767&session_id=session-001&token=secret",
        )

        val status = phoneControllerRuntimeStatus(pairing, runPackage(), null)

        assertEquals(PHONE_CONTROLLER_RUNTIME_STATUS_SCHEMA, status.getString("schema"))
        assertEquals("controller", status.getString("role"))
        assertFalse(status.getBoolean("native_transport_available"))
        assertTrue(status.getString("reason").contains("liblsl_android_class_unavailable"))
        assertTrue(status.getJSONObject("command_protocol").getBoolean("token_required"))
        val commands = status.getJSONObject("command_protocol").getJSONArray("supported_commands")
        val commandNames = (0 until commands.length()).map { commands.getString(it) }
        assertTrue(commandNames.contains("stop_after_block"))
        assertEquals("PPSCommandSignalsV1", status.getJSONObject("streams").getString("command_signals"))

        val descriptions = status.getJSONObject("stream_descriptions")
        assertEquals("pps-android-lsl-stream-descriptions.v1", descriptions.getString("schema"))
        assertEquals("controller", descriptions.getString("role"))
        assertFalse(descriptions.getJSONObject("privacy").getBoolean("demographics_in_stream_name"))

        val commandSignals = descriptions.getJSONObject("command_signals")
        assertEquals("PPSCommandSignalsV1", commandSignals.getString("name"))
        assertEquals("CommandSignals", commandSignals.getString("type"))
        assertEquals("outlet", commandSignals.getString("role"))
        assertEquals(PHONE_LSL_COMMAND_CHANNELS.size, commandSignals.getInt("channel_count"))
        assertEquals("payload_json", commandSignals.getJSONArray("channel_labels").getString(PHONE_LSL_COMMAND_CHANNELS.size - 1))
        assertTrue(commandSignals.getBoolean("token_required"))
        assertTrue(commandSignals.getString("source_id").startsWith("pps-android-controller-signals-v1-part-001-android_controller"))

        val commandAcks = descriptions.getJSONObject("command_acks")
        assertEquals("PPSCommandAcksV1", commandAcks.getString("name"))
        assertEquals("CommandAcks", commandAcks.getString("type"))
        assertEquals("inlet", commandAcks.getString("role"))
        assertEquals(PHONE_LSL_ACK_CHANNELS.size, commandAcks.getInt("channel_count"))
        assertEquals("pps-*-command-acks-v1-*", commandAcks.getString("source_id_pattern"))
    }

    @Test
    fun controllerRuntimeStatusDocumentsNativeControllerTransportWhenEnabled() {
        val pairing = PairingInfo.parse(
            "pps-companion://pair?host=127.0.0.1&port=8767&session_id=session-001&token=secret",
        )
        val bridge = PhoneNativeLslBridgeStatus(
            available = true,
            enabled = false,
            backend = "liblsl-android-reflection",
        )
        val controller = bridge.copy(enabled = true)

        val status = phoneControllerRuntimeStatus(
            pairing = pairing,
            runPackage = runPackage(),
            summary = null,
            nativeBridgeStatus = bridge,
            controllerTransportStatus = controller,
        )

        assertTrue(status.getBoolean("native_transport_available"))
        assertTrue(status.getBoolean("native_controller_transport_enabled"))
        assertEquals("native_lsl_controller_with_local_outbox", status.getString("current_android_source_behavior"))
        assertTrue(status.getJSONObject("native_bridge").getJSONObject("controller_transport").getBoolean("enabled"))
        assertEquals(
            "outlet",
            status.getJSONObject("stream_descriptions")
                .getJSONObject("command_signals")
                .getString("role"),
        )
    }

    private fun runPackage(): MobileRunPackage =
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
                "supported_commands": ["start_experiment", "pause", "resume", "continue_instruction", "stop_after_block", "request_snapshot", "operator_note"]
              },
              "assets": [],
              "blocks": [],
              "building_blocks": [],
              "warnings": []
            }
            """.trimIndent(),
        )
}
