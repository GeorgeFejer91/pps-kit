package io.ppskit.runnercompanion

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class PhoneRunCatalogTest {
    @Test
    fun writesPerRunParticipantAndGlobalCatalogArtifacts() {
        val filesDir = File.createTempFile("pps-phone-catalog", "").apply {
            delete()
            mkdirs()
        }
        val runDir = File(filesDir, "phone_runs/phone-run-001")
        val runPackage = MobilePackageParser.parseManifest(
            """
            {
              "schema": "$MOBILE_PACKAGE_SCHEMA",
              "package_id": "pkg-001",
              "participant_id": "P001",
              "session_id": "session-001",
              "session_group_id": "group-001",
              "part_session_id": "part-001",
              "part_number": "01",
              "title": "Participant P001",
              "mobile_runnable": true,
              "phone_owned_session": true,
              "reconstruction": {"schedule_hash": "schedulehash"},
              "assets": [],
              "building_blocks": [{"asset_id": "trial-a"}],
              "blocks": [{"block_id": "block-01", "index": 1, "label": "Block 01", "trial_count": 2, "trials": [], "tactile_cues": []}],
              "warnings": []
            }
            """.trimIndent(),
        )
        val participantMetadata = JSONObject()
            .put("participant_id", "P001")
            .put("age_years", "30")
            .put("handedness", "right")
            .put("gender", "prefer_not_to_say")
            .put("tactile_threshold_percent", 42.0)
            .put("tactile_threshold_source", "android_haptic_calibration")
        val lslRuntimeStatus = JSONObject()
            .put("native_transport_available", true)
            .put("native_marker_transport_enabled", true)
            .put("command_receiver_available", true)
        val partialSummary = JSONObject()
            .put("total_event_count", 2)
            .put("command_diary_count", 1)
            .put("lsl_marker_mirror_count", 2)
            .put("completion_reason", "in_progress")
        val partialEntry = buildPhoneRunCatalogEntry(
            runPackage = runPackage,
            runId = "phone-run-001",
            runDir = runDir,
            artifactFile = File(runDir, "latest_events.json"),
            complete = false,
            participantMetadata = participantMetadata,
            lslRuntimeStatus = lslRuntimeStatus,
            summary = partialSummary,
        )

        writePhoneRunCatalog(filesDir, runDir, partialEntry)

        val completedSummary = JSONObject(partialSummary.toString())
            .put("total_event_count", 4)
            .put("completion_reason", "completed")
        val completedEntry = buildPhoneRunCatalogEntry(
            runPackage = runPackage,
            runId = "phone-run-001",
            runDir = runDir,
            artifactFile = File(runDir, "completion.json"),
            complete = true,
            participantMetadata = participantMetadata,
            lslRuntimeStatus = lslRuntimeStatus,
            summary = completedSummary,
        )
        val write = writePhoneRunCatalog(filesDir, runDir, completedEntry)

        val entryFile = File(write.getString("entry_path"))
        val participantRunsFile = File(write.getString("participant_runs_path"))
        val indexFile = File(write.getString("index_path"))
        assertTrue(entryFile.isFile)
        assertTrue(participantRunsFile.isFile)
        assertTrue(indexFile.isFile)

        val perRunEntry = JSONObject(entryFile.readText(Charsets.UTF_8))
        assertEquals(PHONE_RUN_CATALOG_ENTRY_SCHEMA, perRunEntry.getString("schema"))
        assertTrue(perRunEntry.getBoolean("completed"))
        assertEquals("completion.json", perRunEntry.getString("artifact_file"))
        assertEquals("30", perRunEntry.getJSONObject("participant_metadata_summary").getString("age_years"))
        assertFalse(perRunEntry.getJSONObject("privacy").getBoolean("demographics_in_stream_name"))

        val rows = participantRunsFile.readLines(Charsets.UTF_8).filter { it.isNotBlank() }
        assertEquals(1, rows.size)
        val row = JSONObject(rows.single())
        assertTrue(row.getBoolean("completed"))
        assertEquals(4, row.getInt("event_count"))

        val index = JSONObject(indexFile.readText(Charsets.UTF_8))
        assertEquals(PHONE_RUN_CATALOG_SCHEMA, index.getString("schema"))
        assertEquals(1, index.getInt("participant_count"))
        assertEquals(1, index.getInt("run_count"))
        assertEquals("phone-run-001", index.getJSONArray("participants").getJSONObject(0).getString("latest_run_id"))
    }
}
