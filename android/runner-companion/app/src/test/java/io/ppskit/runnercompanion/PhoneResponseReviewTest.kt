package io.ppskit.runnercompanion

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PhoneResponseReviewTest {
    @Test
    fun plansTopupFromMissedTactileTrialsAndBuildingBlocks() {
        val runPackage = MobilePackageParser.parseManifest(
            """
            {
              "schema": "$MOBILE_PACKAGE_SCHEMA",
              "package_id": "pkg-001",
              "participant_id": "P001",
              "session_id": "session-001",
              "mobile_runnable": true,
              "phone_owned_session": true,
              "assets": [],
              "building_blocks": [
                {"asset_id": "trial-hit", "filename": "hit.wav", "role": "trial_building_block", "sha256": "h", "trial_type": "audio_tactile", "family": "audio_tactile", "row_label": "inhale", "soa_ms": "100", "noise_type": "white", "duration_s": 4.0, "tactile_onset_s": 1.0},
                {"asset_id": "trial-miss", "filename": "miss.wav", "role": "trial_building_block", "sha256": "m", "trial_type": "audio_tactile", "family": "audio_tactile", "row_label": "exhale", "soa_ms": "300", "noise_type": "pink", "duration_s": 4.0, "tactile_onset_s": 1.0}
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
                    {"trial_number": 1, "trial_uid": "hit-trial", "trial_type": "audio_tactile", "family": "audio_tactile", "soa_ms": "100", "row_label": "inhale", "noise_type": "white", "start_s": 0.0, "end_s": 4.0, "duration_s": 4.0, "tactile_onset_s": 1.0, "building_block_asset_id": "trial-hit"},
                    {"trial_number": 2, "trial_uid": "miss-trial", "trial_type": "audio_tactile", "family": "audio_tactile", "soa_ms": "300", "row_label": "exhale", "noise_type": "pink", "start_s": 4.0, "end_s": 8.0, "duration_s": 4.0, "tactile_onset_s": 1.0, "building_block_asset_id": "trial-miss"}
                  ],
                  "tactile_cues": [
                    {"cue_id": 1, "trial_number": 1, "trial_uid": "hit-trial", "time_s": 1.0, "trial_relative_time_s": 1.0, "soa_ms": "100", "row_label": "inhale", "noise_type": "white"},
                    {"cue_id": 2, "trial_number": 2, "trial_uid": "miss-trial", "time_s": 5.0, "trial_relative_time_s": 1.0, "soa_ms": "300", "row_label": "exhale", "noise_type": "pink"}
                  ]
                }
              ],
              "warnings": []
            }
            """.trimIndent(),
        )
        val events = listOf(
            JSONObject()
                .put("type", "block_complete")
                .put("event_id", 9)
                .put("block_id", "block-01")
                .put("block_index", 1),
            JSONObject()
                .put("type", "tap")
                .put("event_id", 10)
                .put("block_index", 1)
                .put("trial_uid", "hit-trial")
                .put("rt_ms", 220),
        )

        val review = buildPhoneResponseReview(runPackage, events)

        assertEquals(2, review.ledgerRows.size)
        assertEquals(1, review.summary.getInt("hit_count"))
        assertEquals(1, review.summary.getInt("missed_needs_topup_count"))
        assertTrue(review.ledgerRows.first().getBoolean("hit"))
        assertFalse(review.ledgerRows.last().getBoolean("hit"))
        assertEquals("planned_not_played", review.topupPlan.getString("status"))
        assertEquals("pcm_wav_concat_without_ffmpeg", review.topupPlan.getString("synthesis_strategy"))
        val plannedTrial = review.topupPlan.getJSONArray("trials").getJSONObject(0)
        assertEquals("miss-trial", plannedTrial.getString("source_trial_uid"))
        assertEquals("trial-miss", plannedTrial.getString("building_block_asset_id"))
    }
}
