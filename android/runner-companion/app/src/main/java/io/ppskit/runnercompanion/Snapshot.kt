package io.ppskit.runnercompanion

import org.json.JSONArray
import org.json.JSONObject

const val SNAPSHOT_SCHEMA = "pps-runner-companion-snapshot.v1"

data class RunnerSnapshot(
    val sequence: Long,
    val serverUnixMs: Long,
    val serverPerfCounterS: Double,
    val connectionState: String,
    val allowedCommands: Set<String>,
    val participantId: String,
    val setup: SetupStatus,
    val runStatus: RunStatus,
    val partStatus: PartStatus,
    val activeBlock: ActiveBlock,
    val timeline: TimelineState,
    val topupDraftCount: Int,
    val instructionGate: InstructionGate,
    val receivedLocalUnixMs: Long = System.currentTimeMillis(),
) {
    fun canStartPart(partNumber: Int): Boolean = allowedCommands.contains("start_part_$partNumber")
    fun canContinueInstruction(): Boolean = allowedCommands.contains("continue_instruction")
    fun canSubmitSetup(): Boolean = allowedCommands.contains("setup")
    fun canPause(): Boolean = allowedCommands.contains("pause")
    fun canResume(): Boolean = allowedCommands.contains("resume")
}

data class SetupStatus(
    val submitted: Boolean,
    val ready: Boolean,
    val participantNamePresent: Boolean,
    val nameSharingOptIn: Boolean,
    val age: String,
    val handedness: String,
    val gender: String,
)

data class RunStatus(
    val running: Boolean,
    val paused: Boolean,
    val complete: Boolean,
    val stateLabel: String,
    val eventLabel: String,
)

data class PartStatus(
    val availableParts: List<String>,
    val selectedPart: String,
    val currentPackagePart: String,
    val pendingStartPart: String,
)

data class ActiveBlock(
    val active: Boolean,
    val partNumber: String,
    val phaseLabel: String,
    val blockIndex: String,
    val blockLabel: String,
    val durationS: Double,
    val elapsedS: Double,
    val lastAnchorServerPerfCounterS: Double,
    val running: Boolean,
    val paused: Boolean,
    val instructionWaiting: Boolean,
)

data class TimelineState(
    val trialRows: List<TimelineTrial>,
    val tactileCues: List<TactileCue>,
    val clickMarkers: List<TimelineClick>,
    val clicks: Int,
    val tactileTotal: Int,
    val tactilePassed: Int,
)

data class TimelineTrial(
    val trialNumber: Int,
    val trialUid: String,
    val startS: Double,
    val endS: Double,
    val label: String,
    val noiseType: String,
    val soaMs: String,
)

data class TactileCue(
    val cueId: Int,
    val trialNumber: Int,
    val trialUid: String,
    val timeS: Double,
    val rowLabel: String,
    val noiseType: String,
    val soaMs: String,
    val status: String,
)

data class TimelineClick(
    val clickId: Int,
    val timeS: Double,
    val trialUid: String,
    val responseStatus: String,
    val cueId: Int?,
    val cueTrialUid: String,
    val rtS: Double?,
)

data class InstructionGate(
    val waiting: Boolean,
    val part2StartGate: Boolean,
    val instructionLabel: String,
    val buttonLabel: String,
)

object SnapshotParser {
    fun parse(raw: String, receivedLocalUnixMs: Long = System.currentTimeMillis()): RunnerSnapshot {
        val root = JSONObject(raw)
        require(root.optString("schema") == SNAPSHOT_SCHEMA) { "Unsupported snapshot schema." }
        val setup = root.optJSONObject("setup") ?: JSONObject()
        val runStatus = root.optJSONObject("run_status") ?: JSONObject()
        val partStatus = root.optJSONObject("part_status") ?: JSONObject()
        val active = root.optJSONObject("active_block") ?: JSONObject()
        val timeline = root.optJSONObject("timeline") ?: JSONObject()
        val counts = timeline.optJSONObject("counts") ?: JSONObject()
        val instructionGate = root.optJSONObject("instruction_gate") ?: JSONObject()
        val trialRows = timeline.optJSONArray("trial_rows").toTrialRows()
        val tactileCues = timeline.optJSONArray("tactile_cues").toTactileCues()
        val clickMarkers = timeline.optJSONArray("clicks").toTimelineClicks()
        return RunnerSnapshot(
            sequence = root.optLong("sequence", 0),
            serverUnixMs = root.optLong("server_unix_ms", 0),
            serverPerfCounterS = root.optDouble("server_perf_counter_s", 0.0),
            connectionState = root.optString("connection_state", "unknown"),
            allowedCommands = root.optJSONArray("allowed_commands").toStringSet(),
            participantId = root.optJSONObject("participant")?.optString("participant_id").orEmpty(),
            setup = SetupStatus(
                submitted = setup.optBoolean("submitted", false),
                ready = setup.optBoolean("ready", setup.optBoolean("submitted", false)),
                participantNamePresent = setup.optBoolean("participant_name_present", false),
                nameSharingOptIn = setup.optBoolean("name_sharing_opt_in", false),
                age = setup.optString("age", ""),
                handedness = setup.optString("handedness", ""),
                gender = setup.optString("gender", ""),
            ),
            runStatus = RunStatus(
                running = runStatus.optBoolean("running", false),
                paused = runStatus.optBoolean("paused", false),
                complete = runStatus.optBoolean("complete", false),
                stateLabel = runStatus.optString("state_label", ""),
                eventLabel = runStatus.optString("event_label", ""),
            ),
            partStatus = PartStatus(
                availableParts = partStatus.optJSONArray("available_parts").toStringList(),
                selectedPart = partStatus.optString("selected_part", ""),
                currentPackagePart = partStatus.optString("current_package_part", ""),
                pendingStartPart = partStatus.optString("pending_start_part", ""),
            ),
            activeBlock = ActiveBlock(
                active = active.optBoolean("active", false),
                partNumber = active.optString("part_number", ""),
                phaseLabel = active.optString("phase_label", ""),
                blockIndex = active.optString("block_index", ""),
                blockLabel = active.optString("block_label", ""),
                durationS = active.optDouble("duration_s", 0.0).coerceAtLeast(0.0),
                elapsedS = active.optDouble("elapsed_s", 0.0).coerceAtLeast(0.0),
                lastAnchorServerPerfCounterS = active.optDouble("last_anchor_server_perf_counter_s", 0.0),
                running = active.optBoolean("running", false),
                paused = active.optBoolean("paused", false),
                instructionWaiting = active.optBoolean("instruction_waiting", false),
            ),
            timeline = TimelineState(
                trialRows = trialRows,
                tactileCues = tactileCues,
                clickMarkers = clickMarkers,
                clicks = counts.optInt("clicks", clickMarkers.size),
                tactileTotal = counts.optInt("tactile_total", tactileCues.size),
                tactilePassed = counts.optInt("tactile_passed", tactileCues.count { it.status == "passed" || it.status == "recentered" }),
            ),
            topupDraftCount = (root.optJSONObject("topup") ?: JSONObject()).optInt("draft_count", 0),
            instructionGate = InstructionGate(
                waiting = instructionGate.optBoolean("waiting", false),
                part2StartGate = instructionGate.optBoolean("part2_start_gate", false),
                instructionLabel = instructionGate.optString("instruction_label", ""),
                buttonLabel = instructionGate.optString("button_label", "Continue"),
            ),
            receivedLocalUnixMs = receivedLocalUnixMs,
        )
    }
}

private fun JSONArray?.toStringSet(): Set<String> = toStringList().toSet()

private fun JSONArray?.toStringList(): List<String> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { index -> optString(index).takeIf { it.isNotBlank() } }
}

private fun JSONArray?.toTrialRows(): List<TimelineTrial> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { index ->
        val item = optJSONObject(index) ?: return@mapNotNull null
        val startS = item.optDoubleAny("start_s", "start_time_s", "trial_start_s", "onset_s", default = 0.0)
        val explicitEndS = item.optDoubleAny("end_s", "end_time_s", "trial_end_s", default = Double.NaN)
        val durationS = item.optDoubleAny("duration_s", "trial_duration_s", default = Double.NaN)
        val endS = when {
            explicitEndS.isFinite() -> explicitEndS
            durationS.isFinite() -> startS + durationS
            else -> startS
        }.coerceAtLeast(startS)
        TimelineTrial(
            trialNumber = item.optInt("trial_number", 0),
            trialUid = item.optString("trial_uid", ""),
            startS = startS,
            endS = endS,
            label = item.optStringAny("trial_label", "clip_label", "display_label", "label", "family"),
            noiseType = item.optStringAny("noise_type", "noise", "stimulus_type", "stimulus_label"),
            soaMs = item.optStringAny("soa_ms", "soa", "soa_label"),
        )
    }.sortedBy { it.startS }
}

private fun JSONArray?.toTactileCues(): List<TactileCue> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { index ->
        val item = optJSONObject(index) ?: return@mapNotNull null
        TactileCue(
            cueId = item.optInt("cue_id", 0),
            trialNumber = item.optInt("trial_number", 0),
            trialUid = item.optString("trial_uid", ""),
            timeS = item.optDoubleAny("time_s", "tactile_time_s", "onset_s", default = 0.0),
            rowLabel = item.optStringAny("row_label", "phase_label", "label"),
            noiseType = item.optStringAny("noise_type", "noise", "stimulus_type", "stimulus_label"),
            soaMs = item.optStringAny("soa_ms", "soa", "soa_label"),
            status = item.optString("status", ""),
        )
    }.sortedBy { it.timeS }
}

private fun JSONArray?.toTimelineClicks(): List<TimelineClick> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { index ->
        val item = optJSONObject(index) ?: return@mapNotNull null
        TimelineClick(
            clickId = item.optInt("click_id", index + 1),
            timeS = item.optDoubleAny("time_s", "click_time_s", "elapsed_s", "timestamp_s", default = 0.0),
            trialUid = item.optString("trial_uid", ""),
            responseStatus = item.optString("response_status", "off_cue"),
            cueId = if (item.has("cue_id") && !item.isNull("cue_id")) item.optInt("cue_id") else null,
            cueTrialUid = item.optString("cue_trial_uid", ""),
            rtS = if (item.has("rt_s") && !item.isNull("rt_s")) item.optDouble("rt_s") else null,
        )
    }.sortedBy { it.timeS }
}

private fun JSONObject.optDoubleAny(vararg keys: String, default: Double): Double {
    for (key in keys) {
        if (!has(key) || isNull(key)) continue
        val value = optDouble(key, Double.NaN)
        if (value.isFinite()) return value.coerceAtLeast(0.0)
    }
    return default
}

private fun JSONObject.optStringAny(vararg keys: String): String {
    for (key in keys) {
        val value = optString(key, "")
        if (value.isNotBlank()) return value
    }
    return ""
}
