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
    val topupBlockCompleted = events.any {
        it.optString("type") == "block_complete" && it.optString("block_id") == "phone-topup-01"
    }
    val latestTopupMaterialization = events
        .filter { it.optString("type") == "phone_topup_materialization" }
        .lastOrNull()
    val topupOutcomesBySourceTrial = buildPhoneTopupOutcomes(latestTopupMaterialization, tapEvents)

    val sourceLedgerRows = mutableListOf<JSONObject>()
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
            val topupOutcome = topupOutcomesBySourceTrial[trial.trialUid]
            val status = when {
                hit -> "hit"
                topupOutcome?.hit == true -> "missed_rescued_by_topup"
                topupOutcome != null -> "missed_topup_missed"
                else -> "missed_needs_topup"
            }
            val row = JSONObject()
                .put("schema", "pps-android-phone-response-ledger.v1")
                .put("ledger_role", "source_trial")
                .put("block_id", block.blockId)
                .put("block_index", block.index)
                .put("trial_number", trial.trialNumber)
                .put("trial_uid", trial.trialUid)
                .put("cue_id", cue.cueId)
                .put("scheduled_block_time_ms", cueMs)
                .put("response_window_start_ms", cueMs + PHONE_RESPONSE_MIN_RT_MS)
                .put("response_window_end_ms", cueMs + PHONE_RESPONSE_MAX_RT_MS)
                .put("hit", hit)
                .put("status", status)
                .put("rt_ms", if (hit) rtMs else "")
                .put("tap_event_id", hitTap?.optInt("event_id") ?: "")
                .put("building_block_asset_id", trial.buildingBlockAssetId)
                .put("topup_eligible", topupEligible)
                .put("topup_attempted", topupOutcome != null)
                .put("topup_trial_uid", topupOutcome?.topupTrialUid ?: "")
                .put("topup_hit", topupOutcome?.hit ?: JSONObject.NULL)
                .put("topup_rt_ms", topupOutcome?.rtMs ?: "")
                .put("topup_tap_event_id", topupOutcome?.tapEventId ?: "")
            sourceLedgerRows.add(row)
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

    val topupLedgerRows = topupOutcomesBySourceTrial.values
        .sortedWith(compareBy({ it.topupTrialNumber }, { it.sourceTrialUid }))
        .map { it.toLedgerRow() }
    val ledgerRows = sourceLedgerRows + topupLedgerRows
    val hitCount = sourceLedgerRows.count { it.optBoolean("hit") }
    val missedCount = sourceLedgerRows.size - hitCount
    val topupAttemptedCount = topupOutcomesBySourceTrial.size
    val topupHitCount = topupOutcomesBySourceTrial.values.count { it.hit }
    val topupMissCount = topupAttemptedCount - topupHitCount
    val finalUnresolvedMissCount = (missedCount - topupHitCount).coerceAtLeast(0)
    val summary = JSONObject()
        .put("schema", "pps-android-phone-response-summary.v1")
        .put("response_policy", "first_touch_${PHONE_RESPONSE_MIN_RT_MS}_${PHONE_RESPONSE_MAX_RT_MS}_ms_after_tactile")
        .put("eligible_trial_count", sourceLedgerRows.size)
        .put("ledger_row_count", ledgerRows.size)
        .put("hit_count", hitCount)
        .put("missed_needs_topup_count", missedCount)
        .put("topup_rescue_count", topupRows.size)
        .put("topup_attempted_count", topupAttemptedCount)
        .put("topup_hit_count", topupHitCount)
        .put("topup_miss_count", topupMissCount)
        .put("final_rescued_hit_count", topupHitCount)
        .put("final_unresolved_miss_count", finalUnresolvedMissCount)

    val topupPlanStatus = when {
        topupRows.isEmpty() -> "not_needed"
        latestTopupMaterialization?.optString("status") == "skipped" -> "skipped"
        latestTopupMaterialization?.optString("status") == "failed" -> "failed"
        topupBlockCompleted -> "played"
        latestTopupMaterialization?.optString("status") == "materialized" -> "materialized_not_played"
        else -> "planned_not_played"
    }
    val topupPlan = JSONObject()
        .put("schema", "pps-android-phone-topup-plan.v1")
        .put("status", topupPlanStatus)
        .put("synthesis_strategy", "pcm_wav_concat_without_ffmpeg")
        .put("response_min_rt_ms", PHONE_RESPONSE_MIN_RT_MS)
        .put("response_max_rt_ms", PHONE_RESPONSE_MAX_RT_MS)
        .put("missed_trial_count", missedCount)
        .put("topup_trial_count", topupRows.size)
        .put("topup_attempted_count", topupAttemptedCount)
        .put("topup_hit_count", topupHitCount)
        .put("final_unresolved_miss_count", finalUnresolvedMissCount)
        .put("trials", JSONArray().also { array -> topupRows.forEach { array.put(it) } })
    return PhoneResponseReview(ledgerRows = ledgerRows, topupPlan = topupPlan, summary = summary)
}

private data class PhoneTopupOutcome(
    val sourceTrialUid: String,
    val topupTrialUid: String,
    val topupTrialNumber: Int,
    val sourceTrialNumber: Int,
    val buildingBlockAssetId: String,
    val cueMs: Long,
    val hit: Boolean,
    val rtMs: Long,
    val tapEventId: Int,
) {
    fun toLedgerRow(): JSONObject =
        JSONObject()
            .put("schema", "pps-android-phone-response-ledger.v1")
            .put("ledger_role", "topup_rescue")
            .put("source_trial_uid", sourceTrialUid)
            .put("source_trial_number", sourceTrialNumber)
            .put("trial_uid", topupTrialUid)
            .put("trial_number", topupTrialNumber)
            .put("block_id", "phone-topup-01")
            .put("block_index", "")
            .put("scheduled_block_time_ms", cueMs)
            .put("response_window_start_ms", cueMs + PHONE_RESPONSE_MIN_RT_MS)
            .put("response_window_end_ms", cueMs + PHONE_RESPONSE_MAX_RT_MS)
            .put("hit", hit)
            .put("status", if (hit) "topup_hit" else "topup_miss")
            .put("rt_ms", if (hit) rtMs else "")
            .put("tap_event_id", if (hit) tapEventId else "")
            .put("building_block_asset_id", buildingBlockAssetId)
}

private fun buildPhoneTopupOutcomes(
    materializationEvent: JSONObject?,
    tapEvents: List<JSONObject>,
): Map<String, PhoneTopupOutcome> {
    if (materializationEvent == null || materializationEvent.optString("status") != "materialized") return emptyMap()
    val trials = materializationEvent.optJSONArray("trials") ?: return emptyMap()
    val outcomes = linkedMapOf<String, PhoneTopupOutcome>()
    for (index in 0 until trials.length()) {
        val trial = trials.optJSONObject(index) ?: continue
        val sourceTrialUid = trial.optString("source_trial_uid", "")
        val topupTrialUid = trial.optString("topup_trial_uid", "")
        if (sourceTrialUid.isBlank() || topupTrialUid.isBlank()) continue
        val tactileOnsetS = trial.optNullableDouble("tactile_onset_s") ?: continue
        val topupStartS = trial.optDouble("topup_start_s", 0.0)
        val cueMs = ((topupStartS + tactileOnsetS) * 1000.0).roundToLong()
        val hitTap = tapEvents.firstOrNull { event ->
            event.optString("trial_uid") == topupTrialUid &&
                event.optLong("rt_ms", Long.MIN_VALUE) in PHONE_RESPONSE_MIN_RT_MS..PHONE_RESPONSE_MAX_RT_MS
        }
        val rtMs = hitTap?.optLong("rt_ms", -1L) ?: -1L
        outcomes[sourceTrialUid] = PhoneTopupOutcome(
            sourceTrialUid = sourceTrialUid,
            topupTrialUid = topupTrialUid,
            topupTrialNumber = trial.optInt("topup_trial_number", index + 1),
            sourceTrialNumber = trial.optInt("source_trial_number", 0),
            buildingBlockAssetId = trial.optString("building_block_asset_id", ""),
            cueMs = cueMs,
            hit = hitTap != null,
            rtMs = rtMs,
            tapEventId = hitTap?.optInt("event_id") ?: 0,
        )
    }
    return outcomes
}

private fun JSONObject.optNullableDouble(key: String): Double? {
    if (!has(key) || isNull(key)) return null
    return optDouble(key, Double.NaN).takeIf { it.isFinite() }
}
