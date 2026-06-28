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
                  "title": "Participant P001",
                  "block_count": 1,
                  "trial_count": 2,
                  "asset_count": 1,
                  "total_asset_bytes": 12,
                  "mobile_runnable": true,
                  "warnings": []
                }
              ]
            }
            """.trimIndent(),
        )
        assertEquals("pkg-001", list.activePackageId)
        assertEquals(1, list.packages.size)
        assertTrue(list.packages.first().mobileRunnable)

        val manifest = MobilePackageParser.parseManifest(
            """
            {
              "schema": "$MOBILE_PACKAGE_SCHEMA",
              "package_id": "pkg-001",
              "participant_id": "P001",
              "session_id": "session-001",
              "title": "Participant P001",
              "mobile_runnable": true,
              "warnings": [],
              "assets": [
                {"asset_id": "block-01-audio", "filename": "block.wav", "media_type": "audio/wav", "size_bytes": 12, "sha256": "abc", "available": true}
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
                    {"trial_number": 1, "trial_uid": "trial-a", "trial_type": "audio_tactile", "family": "audio_tactile", "soa_ms": "300", "row_label": "inhale", "noise_type": "white", "start_s": 2.0, "end_s": 6.0, "duration_s": 4.0, "tactile_onset_s": 1.25}
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
        assertEquals("block-01-audio", manifest.blocks.first().audioAssetId)
        assertEquals("trial-a", manifest.blocks.first().trials.first().trialUid)
        assertEquals(3.25, manifest.blocks.first().tactileCues.first().timeS, 0.001)
        assertEquals("abc", manifest.asset("block-01-audio")?.sha256)
    }
}
