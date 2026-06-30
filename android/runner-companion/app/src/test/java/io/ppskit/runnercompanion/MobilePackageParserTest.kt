package io.ppskit.runnercompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MobilePackageParserTest {
    @Test
    fun parsesPackageListAndManifest() {
        val list = MobilePackageParser.parseList(
            """
            {
              "schema": "$MOBILE_PACKAGE_LIST_SCHEMA",
              "active_package_id": "pkg-001",
              "packages": [
                {
                  "package_id": "pkg-001",
                  "participant_id": "P001",
                  "session_id": "session-001",
                  "session_group_id": "group-001",
                  "part_session_id": "part-001",
                  "part_number": "1",
                  "title": "Participant P001",
                  "block_count": 1,
                  "trial_count": 2,
                  "asset_count": 1,
                  "total_asset_bytes": 12,
                  "mobile_runnable": true,
                  "phone_owned_session": true,
                  "warnings": []
                }
              ]
            }
            """.trimIndent(),
        )
        assertEquals("pkg-001", list.activePackageId)
        assertEquals(1, list.packages.size)
        assertEquals("group-001", list.packages.first().sessionGroupId)
        assertEquals("part-001", list.packages.first().partSessionId)
        assertEquals("1", list.packages.first().partNumber)
        assertTrue(list.packages.first().mobileRunnable)
        assertTrue(list.packages.first().phoneOwnedSession)

        val manifest = MobilePackageParser.parseManifest(
            """
            {
              "schema": "$MOBILE_PACKAGE_SCHEMA",
              "package_id": "pkg-001",
              "participant_id": "P001",
              "session_id": "session-001",
              "session_group_id": "group-001",
              "part_session_id": "part-001",
              "part_number": "1",
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
                "segment5_block_csvs": [
                  {"block_id": "block-01", "sha256": "blockhash"}
                ]
              },
              "reconstruction": {
                "schema": "pps-mobile-reconstruction-contract.v1",
                "authority": "android_phone",
                "fallback_execution_strategy": "prepared_block_wavs",
                "preferred_lightweight_strategy": "replay_schedule_from_trial_building_blocks",
                "package_asset_strategy": "trial_building_blocks_only",
                "study_hierarchy": [
                  "study_profile",
                  "segment_1_audio_ingredients",
                  "segment_2_trial_sequence_designs",
                  "segment_3_tactile_baseline_catch_trials",
                  "segment_4_trial_repetition_pool",
                  "segment_5_block_csv_preview",
                  "segment_6_participant_part_order",
                  "phone_runtime_package",
                  "phone_runtime_events"
                ],
                "source_run_setup_manifest_path": "runs/setup.json",
                "source_run_setup_sha256": "runhash",
                "schedule_hash": "schedulehash",
                "building_block_count": 1,
                "block_count": 1,
                "trial_count": 2
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
              "warnings": [],
              "assets": [
                {"asset_id": "block-01-audio", "filename": "block.wav", "media_type": "audio/wav", "role": "block_audio", "size_bytes": 12, "sha256": "abc", "available": true}
              ],
              "building_blocks": [
                {"asset_id": "trial-1", "filename": "trial.wav", "role": "trial_building_block", "sha256": "trialhash", "trial_type": "audio_tactile", "family": "audio_tactile", "row_label": "inhale", "soa_ms": "300", "noise_type": "white", "duration_s": 4.0, "tactile_onset_s": 1.25}
              ],
              "blocks": [
                {
                  "block_id": "block-01",
                  "index": 1,
                  "label": "Block 01",
                  "duration_s": 10.0,
                  "trial_count": 2,
                  "audio_asset_id": "block-01-audio",
                  "trials": [
                    {"trial_number": 1, "trial_uid": "trial-a", "trial_type": "audio_tactile", "family": "audio_tactile", "soa_ms": "300", "row_label": "inhale", "noise_type": "white", "start_s": 2.0, "end_s": 6.0, "duration_s": 4.0, "tactile_onset_s": 1.25, "building_block_asset_id": "trial-1"}
                  ],
                  "tactile_cues": [
                    {"cue_id": 1, "trial_number": 1, "trial_uid": "trial-a", "time_s": 3.25, "trial_relative_time_s": 1.25, "soa_ms": "300", "row_label": "inhale", "noise_type": "white"}
                  ]
                }
              ]
            }
            """.trimIndent(),
        )

        assertEquals("pkg-001", manifest.packageId)
        assertEquals("group-001", manifest.sessionGroupId)
        assertTrue(manifest.phoneOwnedSession)
        assertEquals(listOf("P001", "P002"), manifest.participantRoster)
        assertEquals("seed-123", manifest.randomizationSeed)
        assertEquals("pps-mobile-source-segment-hashes.v1", manifest.sourceSegmentHashes.schema)
        assertEquals("segment5hash", manifest.sourceSegmentHashes.sourceSegment5ManifestSha256)
        assertEquals(1, manifest.sourceSegmentHashes.segment5BlockCsvCount)
        assertEquals("block-01-audio", manifest.blocks.first().audioAssetId)
        assertEquals("trial-a", manifest.blocks.first().trials.first().trialUid)
        assertEquals("trial-1", manifest.blocks.first().trials.first().buildingBlockAssetId)
        assertEquals(3.25, manifest.blocks.first().tactileCues.first().timeS, 0.001)
        assertEquals("abc", manifest.asset("block-01-audio")?.sha256)
        assertEquals("trial-1", manifest.buildingBlocks.first().assetId)
        assertEquals("schedulehash", manifest.reconstruction.scheduleHash)
        assertEquals("trial_building_blocks_only", manifest.reconstruction.packageAssetStrategy)
        assertEquals("segment_6_participant_part_order", manifest.reconstruction.studyHierarchy[6])
        assertEquals("runs/setup.json", manifest.reconstruction.sourceRunSetupManifestPath)
        assertEquals("PPSMarkersV2", manifest.lsl.richMarkersName)
        assertTrue(manifest.lsl.supportedCommands.contains("pause"))
        assertTrue(manifest.rawManifestJson.contains("\"package_id\""))
    }

    @Test
    fun stillParsesLegacyV1Manifest() {
        val manifest = MobilePackageParser.parseManifest(
            """
            {
              "schema": "$MOBILE_PACKAGE_SCHEMA_V1",
              "package_id": "pkg-v1",
              "participant_id": "P001",
              "session_id": "session-001",
              "blocks": [],
              "assets": [],
              "mobile_runnable": true
            }
            """.trimIndent(),
        )

        assertEquals("pkg-v1", manifest.packageId)
        assertEquals("", manifest.reconstruction.schema)
    }
}
