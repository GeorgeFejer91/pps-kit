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
              "participant_roster": ["P001", "P002"],
              "randomization_seed": "seed-123",
              "source_segment_hashes": {
                "schema": "pps-mobile-source-segment-hashes.v1",
                "source_run_setup_manifest_sha256": "runhash",
                "source_segment5_manifest_sha256": "segment5hash",
                "segment6_order_csv_sha256": "orderhash",
                "segment5_block_csvs": [{"block_id": "block-01", "sha256": "blockhash"}]
              },
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
            .put(
                "haptic_capability_summary",
                JSONObject()
                    .put("schema", "pps-android-lsl-haptic-capability-summary.v1")
                    .put("has_vibrator", true)
                    .put("has_amplitude_control", true)
                    .put("calibration_policy", "amplitude_percent_supported")
                    .put("calibration_status", "threshold_detected")
                    .put("recommended_threshold_percent", 42.0)
                    .put("recommended_amplitude", 107),
            )
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
            .put("native_lsl_pushed_count", 4)
            .put("native_lsl_failed_count", 0)
            .put("native_lsl_rich_marker_pushed_count", 4)
            .put("native_lsl_rich_marker_failed_count", 0)
            .put("native_lsl_numeric_trigger_pushed_count", 4)
            .put("native_lsl_numeric_trigger_failed_count", 0)
            .put("native_lsl_command_received_count", 1)
            .put("native_lsl_command_ack_count", 1)
            .put("native_lsl_command_ack_failed_count", 0)
            .put("native_lsl_command_rejected_count", 0)
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
        assertEquals("seed-123", perRunEntry.getString("randomization_seed"))
        assertEquals(2, perRunEntry.getInt("participant_roster_count"))
        assertEquals("segment5hash", perRunEntry.getJSONObject("source_segment_hashes").getString("source_segment5_manifest_sha256"))
        assertEquals("30", perRunEntry.getJSONObject("participant_metadata_summary").getString("age_years"))
        assertEquals(107, perRunEntry.getJSONObject("haptic_capability_summary").getInt("recommended_amplitude"))
        assertEquals(4, perRunEntry.getInt("native_lsl_pushed_count"))
        assertEquals(1, perRunEntry.getInt("native_lsl_command_received_count"))
        assertEquals(1, perRunEntry.getInt("native_lsl_command_ack_count"))
        assertEquals(0, perRunEntry.getInt("native_lsl_command_rejected_count"))
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

    @Test
    fun writesPhoneOwnedDataMinAndDataMaxExport() {
        val filesDir = File.createTempFile("pps-phone-data-export", "").apply {
            delete()
            mkdirs()
        }
        val runDir = File(filesDir, "phone_runs/phone-run-001").apply { mkdirs() }
        File(runDir, "completion.json").writeText("{}", Charsets.UTF_8)
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
              "building_blocks": [{"asset_id": "trial-hit"}, {"asset_id": "trial-miss"}],
              "blocks": [
                {
                  "block_id": "block-01",
                  "index": 1,
                  "label": "Block 01",
                  "duration_s": 8.0,
                  "trial_count": 2,
                  "trials": [
                    {"trial_number": 1, "trial_uid": "trial-hit", "trial_type": "audio_tactile", "family": "audio_tactile", "soa_ms": "100", "row_label": "inhale", "noise_type": "white", "start_s": 0.0, "end_s": 4.0, "duration_s": 4.0, "tactile_onset_s": 1.0, "building_block_asset_id": "trial-hit"},
                    {"trial_number": 2, "trial_uid": "trial-miss", "trial_type": "audio_tactile", "family": "audio_tactile", "soa_ms": "300", "row_label": "exhale", "noise_type": "pink", "start_s": 4.0, "end_s": 8.0, "duration_s": 4.0, "tactile_onset_s": 1.0, "building_block_asset_id": "trial-miss"}
                  ],
                  "tactile_cues": []
                }
              ],
              "warnings": []
            }
            """.trimIndent(),
        )
        val entry = JSONObject()
            .put("run_id", "phone-run-001")
            .put("participant_id", "P001")
        val ledgerRows = listOf(
            JSONObject()
                .put("ledger_role", "source_trial")
                .put("block_index", 1)
                .put("trial_number", 1)
                .put("trial_uid", "trial-hit")
                .put("hit", true)
                .put("rt_ms", 220),
            JSONObject()
                .put("ledger_role", "source_trial")
                .put("block_index", 1)
                .put("trial_number", 2)
                .put("trial_uid", "trial-miss")
                .put("hit", false)
                .put("status", "missed_rescued_by_topup"),
            JSONObject()
                .put("ledger_role", "topup_rescue")
                .put("source_trial_uid", "trial-miss")
                .put("trial_number", 1)
                .put("trial_uid", "phone-topup-1-trial-miss")
                .put("hit", true)
                .put("rt_ms", 260),
        )

        val export = writePhoneOwnedDataExport(
            filesDir = filesDir,
            runPackage = runPackage,
            runDir = runDir,
            catalogEntry = entry,
            responseLedgerRows = ledgerRows,
        )

        assertEquals(PHONE_OWNED_DATA_EXPORT_SCHEMA, export.getString("schema"))
        assertEquals("group-001", export.getString("session_group_id"))
        assertEquals(3, export.getInt("data_min_row_count"))
        val participantCsv = File(export.getString("data_min_participant_csv"))
        val masterCsv = File(export.getString("data_min_master_successful_participants_csv"))
        val dataMaxRunDir = File(export.getString("data_max_run_dir"))
        assertTrue(participantCsv.isFile)
        assertTrue(masterCsv.isFile)
        assertTrue(dataMaxRunDir.resolve("completion.json").isFile)
        assertTrue(dataMaxRunDir.resolve("phone_owned_data_export.json").isFile)
        val portablePaths = export.getJSONObject("portable_paths")
        assertEquals(".", portablePaths.getString("archive_run_root"))
        assertEquals("phone_owned_exports", portablePaths.getString("phone_owned_exports_root"))
        assertEquals("phone_owned_exports/1.Data_min/P001.csv", portablePaths.getString("data_min_participant_csv"))
        assertEquals(
            "phone_owned_exports/1.Data_min/master_successful_participants.csv",
            portablePaths.getString("data_min_master_successful_participants_csv"),
        )
        assertEquals(
            "phone_owned_exports/2.Data_max/P001/runs/phone-run-001",
            portablePaths.getString("data_max_run_dir"),
        )
        assertEquals(
            "phone_owned_exports/2.Data_max/P001/runs/phone-run-001/phone_owned_data_export.json",
            portablePaths.getString("data_max_phone_owned_data_export"),
        )
        val rows = participantCsv.readLines(Charsets.UTF_8)
        assertEquals(PHONE_DATA_MIN_FIELDNAMES.joinToString(","), rows.first())
        assertEquals(4, rows.size)
        assertTrue(rows[1].contains("trial-hit,audio_tactile,Inhale,white,audio_tactile,100,true,Hit,220"))
        assertTrue(rows[2].contains("trial-miss,audio_tactile,Exhale,pink,audio_tactile,300,false,Miss,"))
        assertTrue(rows[3].contains("Phone top-up,1,3,phone-topup-1-trial-miss,audio_tactile,Exhale,pink,audio_tactile,300,true,Hit,260"))
        assertEquals(rows, masterCsv.readLines(Charsets.UTF_8))
        val artifact = JSONObject(File(export.getString("artifact_path")).readText(Charsets.UTF_8))
        assertFalse(artifact.getJSONObject("privacy").getBoolean("demographics_in_stream_name"))
    }
}
