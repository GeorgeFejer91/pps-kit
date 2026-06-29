package io.ppskit.runnercompanion

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.roundToLong

internal const val PHONE_RESPONSE_MIN_RT_MS = 100L
internal const val PHONE_RESPONSE_MAX_RT_MS = 1300L

internal data class PhoneResponseReview(
    val ledgerRows: List<JSONObject>,
    val topupPlan: JSONObject,
    val summary: JSONObject,
)

internal fun buildPhoneResponseReview(
    runPackage: MobileRunPackage,
    events: List<JSONObject>,
): PhoneResponseReview {
    val tapEvents = events
        .filter { it.optString("type") == "tap" && it.optString("trial_uid").isNotBlank() }
        .sortedWith(compareBy({ it.optInt("event_id", Int.MAX_VALUE) }, { it.optLong("phone_elapsed_realtime_ms", Long.MAX_VALUE) }))
    val completedBlockIds = events
        .filter { it.optString("type") == "block_complete" }
        .mapNotNull { it.optString("block_id").takeIf { value -> value.isNotBlank() } }
        .toSet()
    val completedBlockIndexes = events
        .filter { it.optString("type") == "block_complete" }
        .mapNotNull { it.optInt("block_index", -1).takeIf { value -> value > 0 } }
        .toSet()

    val ledgerRows = mutableListOf<JSONObject>()
    val topupRows = mutableListOf<JSONObject>()
    for (block in runPackage.blocks.sortedBy { it.index }) {
        val blockCompleted = block.blockId in completedBlockIds || block.index in completedBlockIndexes
        if (!blockCompleted) continue
        val cuesByTrialUid = block.tactileCues.associateBy { it.trialUid }
        for (trial in block.trials.sortedBy { it.startS }) {
            val cue = cuesByTrialUid[trial.trialUid] ?: continue
            val cueMs = (cue.timeS * 1000.0).roundToLong()
            val hitTap = tapEvents.firstOrNull { event ->
                event.optString("trial_uid") == trial.trialUid &&
                    event.optInt("block_index", block.index) == block.index &&
                    event.optLong("rt_ms", Long.MIN_VALUE) in PHONE_RESPONSE_MIN_RT_MS..PHONE_RESPONSE_MAX_RT_MS
            }
            val rtMs = hitTap?.optLong("rt_ms", -1L) ?: -1L
            val hit = hitTap != null
            val topupEligible = !hit && trial.buildingBlockAssetId.isNotBlank()
            val row = JSONObject()
                .put("schema", "pps-android-phone-response-ledger.v1")
                .put("block_id", block.blockId)
                .put("block_index", block.index)
                .put("trial_number", trial.trialNumber)
                .put("trial_uid", trial.trialUid)
                .put("cue_id", cue.cueId)
                .put("scheduled_block_time_ms", cueMs)
                .put("response_window_start_ms", cueMs + PHONE_RESPONSE_MIN_RT_MS)
                .put("response_window_end_ms", cueMs + PHONE_RESPONSE_MAX_RT_MS)
                .put("hit", hit)
                .put("status", if (hit) "hit" else "missed_needs_topup")
                .put("rt_ms", if (hit) rtMs else "")
                .put("tap_event_id", hitTap?.optInt("event_id") ?: "")
                .put("building_block_asset_id", trial.buildingBlockAssetId)
                .put("topup_eligible", topupEligible)
            ledgerRows.add(row)
            if (topupEligible) {
                topupRows.add(
                    JSONObject()
                        .put("topup_role", "rescue")
                        .put("source_block_id", block.blockId)
                        .put("source_block_index", block.index)
                        .put("source_trial_uid", trial.trialUid)
                        .put("source_trial_number", trial.trialNumber)
                        .put("building_block_asset_id", trial.buildingBlockAssetId)
                        .put("trial_type", trial.trialType)
                        .put("family", trial.family)
                        .put("soa_ms", trial.soaMs)
                        .put("row_label", trial.rowLabel)
                        .put("noise_type", trial.noiseType)
                        .put("duration_s", trial.durationS)
                        .put("tactile_onset_s", trial.tactileOnsetS)
                        .put("response_window_onset_s", trial.responseWindowOnsetS),
                )
            }
        }
    }

    val hitCount = ledgerRows.count { it.optBoolean("hit") }
    val missedCount = ledgerRows.size - hitCount
    val summary = JSONObject()
        .put("schema", "pps-android-phone-response-summary.v1")
        .put("response_policy", "first_touch_${PHONE_RESPONSE_MIN_RT_MS}_${PHONE_RESPONSE_MAX_RT_MS}_ms_after_tactile")
        .put("eligible_trial_count", ledgerRows.size)
        .put("hit_count", hitCount)
        .put("missed_needs_topup_count", missedCount)
        .put("topup_rescue_count", topupRows.size)

    val topupPlan = JSONObject()
        .put("schema", "pps-android-phone-topup-plan.v1")
        .put("status", if (topupRows.isEmpty()) "not_needed" else "planned_not_played")
        .put("synthesis_strategy", "pcm_wav_concat_without_ffmpeg")
        .put("response_min_rt_ms", PHONE_RESPONSE_MIN_RT_MS)
        .put("response_max_rt_ms", PHONE_RESPONSE_MAX_RT_MS)
        .put("missed_trial_count", missedCount)
        .put("topup_trial_count", topupRows.size)
        .put("trials", JSONArray().also { array -> topupRows.forEach { array.put(it) } })
    return PhoneResponseReview(ledgerRows = ledgerRows, topupPlan = topupPlan, summary = summary)
}
