package io.ppskit.runnercompanion

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PhoneNativeLslBridgeTest {
    @Test
    fun bridgeReportsUnavailableWhenLiblslAndroidAarIsAbsent() {
        val bridge = PhoneNativeLslBridgeFactory.create()
        val status = bridge.status()

        assertFalse(status.available)
        assertFalse(status.enabled)
        assertEquals("liblsl-android-reflection", status.backend)
        assertTrue(status.reason.contains("liblsl_android_class_unavailable"))
    }

    @Test
    fun bridgeStatusJsonDocumentsExpectedNativeStreamsAndMarkerChannels() {
        val status = phoneNativeLslStatusJson(
            PhoneNativeLslBridgeStatus(
                available = false,
                enabled = false,
                backend = "liblsl-android-reflection",
                reason = "missing",
            ),
        )

        assertEquals("PPSMarkersV2", status.getJSONObject("stream_names").getString("rich_markers"))
        assertEquals("PPSTriggerCodes", status.getJSONObject("stream_names").getString("numeric_triggers"))
        assertEquals("marker_version", status.getJSONArray("marker_channels").getString(0))
        assertEquals("payload_json", status.getJSONArray("marker_channels").getString(PHONE_LSL_MARKER_CHANNELS.size - 1))
    }

    @Test
    fun markerJsonConvertsToPcCompatibleRichSampleAndNumericCode() {
        val marker = JSONObject()
            .put("marker_version", "2.0")
            .put("event_id", 7)
            .put("event_type", "vibration_cue")
            .put("event_code", 500)
            .put("trigger_key", "trial:cue")
            .put("marker_name", "P001_block01_tactile")
            .put("session_id", "session-001")
            .put("participant_id", "P001")
            .put("session_group_id", "group-001")
            .put("part_session_id", "part-001")
            .put("part_number", "1")
            .put("block_index", "1")
            .put("trial_uid", "trial-a")
            .put("sample_index", "44100")
            .put("timestamp_quality", "android_elapsed_realtime")
            .put("payload_json", "{\"ok\":true}")

        val sample = phoneMarkerToRichSample(marker)

        assertEquals(PHONE_LSL_MARKER_CHANNELS.size, sample.size)
        assertEquals("2.0", sample[0])
        assertEquals("vibration_cue", sample[2])
        assertEquals("500", sample[3])
        assertEquals("trial-a", sample[12])
        assertEquals("{\"ok\":true}", sample[15])
        assertEquals(500, phoneMarkerTriggerCode(marker))
    }
}
