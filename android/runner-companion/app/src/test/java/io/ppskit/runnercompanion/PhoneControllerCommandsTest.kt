package io.ppskit.runnercompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

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
    fun controllerRuntimeStatusDeclaresStrictNativeBoundary() {
        val pairing = PairingInfo.parse(
            "pps-companion://pair?host=127.0.0.1&port=8767&session_id=session-001&token=secret",
        )

        val status = phoneControllerRuntimeStatus(pairing, runPackage(), null)

        assertEquals(PHONE_CONTROLLER_RUNTIME_STATUS_SCHEMA, status.getString("schema"))
        assertEquals("controller", status.getString("role"))
        assertFalse(status.getBoolean("native_transport_available"))
        assertEquals("native_liblsl_android_layer_not_present", status.getString("reason"))
        assertTrue(status.getJSONObject("command_protocol").getBoolean("token_required"))
        assertEquals("PPSCommandSignalsV1", status.getJSONObject("streams").getString("command_signals"))
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
                "supported_commands": ["start_experiment", "pause", "resume", "continue_instruction", "request_snapshot"]
              },
              "assets": [],
              "blocks": [],
              "building_blocks": [],
              "warnings": []
            }
            """.trimIndent(),
        )
}
