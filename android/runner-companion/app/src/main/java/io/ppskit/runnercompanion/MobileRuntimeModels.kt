package io.ppskit.runnercompanion

import org.json.JSONArray
import org.json.JSONObject

const val MOBILE_PACKAGE_LIST_SCHEMA = "pps-mobile-run-package-list.v2"
const val MOBILE_PACKAGE_SCHEMA = "pps-mobile-run-package.v2"
const val MOBILE_PACKAGE_LIST_SCHEMA_V1 = "pps-mobile-run-package-list.v1"
const val MOBILE_PACKAGE_SCHEMA_V1 = "pps-mobile-run-package.v1"

data class MobilePackageList(
    val activePackageId: String,
    val packages: List<MobilePackageSummary>,
)

data class MobilePackageSummary(
    val packageId: String,
    val participantId: String,
    val sessionId: String,
    val title: String,
    val blockCount: Int,
    val trialCount: Int,
    val assetCount: Int,
    val totalAssetBytes: Long,
    val mobileRunnable: Boolean,
    val phoneOwnedSession: Boolean,
    val warnings: List<String>,
)

data class MobileRunPackage(
    val packageId: String,
    val participantId: String,
    val sessionId: String,
    val sessionGroupId: String,
    val partSessionId: String,
    val partNumber: String,
    val title: String,
    val blocks: List<MobileBlock>,
    val assets: List<MobileAsset>,
    val buildingBlocks: List<MobileBuildingBlock>,
    val reconstruction: MobileReconstructionContract,
    val lsl: MobileLslContract,
    val mobileRunnable: Boolean,
    val phoneOwnedSession: Boolean,
    val warnings: List<String>,
    val rawManifestJson: String = "",
) {
    fun asset(assetId: String): MobileAsset? = assets.firstOrNull { it.assetId == assetId }
}

data class MobileAsset(
    val assetId: String,
    val filename: String,
    val mediaType: String,
    val role: String,
    val sizeBytes: Long,
    val sha256: String,
    val available: Boolean,
)

data class MobileBuildingBlock(
    val assetId: String,
    val filename: String,
    val role: String,
    val sha256: String,
    val trialType: String,
    val family: String,
    val rowLabel: String,
    val soaMs: String,
    val noiseType: String,
    val durationS: Double,
    val tactileOnsetS: Double?,
    val responseWindowOnsetS: Double?,
)

data class MobileReconstructionContract(
    val schema: String,
    val authority: String,
    val fallbackExecutionStrategy: String,
    val preferredLightweightStrategy: String,
    val sourceRunSetupSha256: String,
    val scheduleHash: String,
    val buildingBlockCount: Int,
    val blockCount: Int,
    val trialCount: Int,
) {
    companion object {
        val empty = MobileReconstructionContract("", "", "", "", "", "", 0, 0, 0)
    }
}

data class MobileLslContract(
    val schema: String,
    val runtimeAuthority: String,
    val privacyDefault: String,
    val richMarkersName: String,
    val numericTriggersName: String,
    val commandSignalsName: String,
    val commandAcksName: String,
    val nativeAndroidLslRequired: Boolean,
    val currentAndroidSourceBehavior: String,
    val supportedCommands: List<String>,
) {
    companion object {
        val empty = MobileLslContract("", "", "", "", "", "", "", false, "", emptyList())
    }
}

data class MobileBlock(
    val blockId: String,
    val index: Int,
    val label: String,
    val durationS: Double,
    val trialCount: Int,
    val audioAssetId: String,
    val trials: List<MobileTrial>,
    val tactileCues: List<MobileCue>,
)

data class MobileTrial(
    val trialNumber: Int,
    val trialUid: String,
    val trialType: String,
    val family: String,
    val soaMs: String,
    val rowLabel: String,
    val noiseType: String,
    val startS: Double,
    val endS: Double,
    val durationS: Double,
    val tactileOnsetS: Double?,
    val responseWindowOnsetS: Double?,
    val buildingBlockAssetId: String,
)

data class MobileCue(
    val cueId: Int,
    val trialNumber: Int,
    val trialUid: String,
    val timeS: Double,
    val trialRelativeTimeS: Double,
    val soaMs: String,
    val rowLabel: String,
    val noiseType: String,
)

object MobilePackageParser {
    fun parseList(raw: String): MobilePackageList {
        val root = JSONObject(raw)
        require(root.optString("schema") in setOf(MOBILE_PACKAGE_LIST_SCHEMA, MOBILE_PACKAGE_LIST_SCHEMA_V1)) {
            "Unsupported mobile package list schema."
        }
        return MobilePackageList(
            activePackageId = root.optString("active_package_id", ""),
            packages = root.optJSONArray("packages").toPackageSummaries(),
        )
    }

    fun parseManifest(raw: String): MobileRunPackage {
        val root = JSONObject(raw)
        require(root.optString("schema") in setOf(MOBILE_PACKAGE_SCHEMA, MOBILE_PACKAGE_SCHEMA_V1)) {
            "Unsupported mobile package schema."
        }
        return MobileRunPackage(
            packageId = root.optString("package_id", ""),
            participantId = root.optString("participant_id", ""),
            sessionId = root.optString("session_id", ""),
            sessionGroupId = root.optString("session_group_id", ""),
            partSessionId = root.optString("part_session_id", ""),
            partNumber = root.optString("part_number", ""),
            title = root.optString("title", ""),
            blocks = root.optJSONArray("blocks").toMobileBlocks(),
            assets = root.optJSONArray("assets").toMobileAssets(),
            buildingBlocks = root.optJSONArray("building_blocks").toMobileBuildingBlocks(),
            reconstruction = root.optJSONObject("reconstruction").toMobileReconstructionContract(),
            lsl = root.optJSONObject("lsl").toMobileLslContract(),
            mobileRunnable = root.optBoolean("mobile_runnable", false),
            phoneOwnedSession = root.optBoolean("phone_owned_session", false),
            warnings = root.optJSONArray("warnings").toStringList(),
            rawManifestJson = root.toString(2),
        )
    }
}

private fun JSONArray?.toPackageSummaries(): List<MobilePackageSummary> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { index ->
        val item = optJSONObject(index) ?: return@mapNotNull null
        MobilePackageSummary(
            packageId = item.optString("package_id", ""),
            participantId = item.optString("participant_id", ""),
            sessionId = item.optString("session_id", ""),
            title = item.optString("title", ""),
            blockCount = item.optInt("block_count", 0),
            trialCount = item.optInt("trial_count", 0),
            assetCount = item.optInt("asset_count", 0),
            totalAssetBytes = item.optLong("total_asset_bytes", 0L),
            mobileRunnable = item.optBoolean("mobile_runnable", false),
            phoneOwnedSession = item.optBoolean("phone_owned_session", false),
            warnings = item.optJSONArray("warnings").toStringList(),
        )
    }
}

private fun JSONArray?.toMobileAssets(): List<MobileAsset> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { index ->
        val item = optJSONObject(index) ?: return@mapNotNull null
        MobileAsset(
            assetId = item.optString("asset_id", ""),
            filename = item.optString("filename", ""),
            mediaType = item.optString("media_type", "application/octet-stream"),
            role = item.optString("role", ""),
            sizeBytes = item.optLong("size_bytes", 0L),
            sha256 = item.optString("sha256", ""),
            available = item.optBoolean("available", true),
        )
    }
}

private fun JSONArray?.toMobileBuildingBlocks(): List<MobileBuildingBlock> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { index ->
        val item = optJSONObject(index) ?: return@mapNotNull null
        MobileBuildingBlock(
            assetId = item.optString("asset_id", ""),
            filename = item.optString("filename", ""),
            role = item.optString("role", "trial_building_block"),
            sha256 = item.optString("sha256", ""),
            trialType = item.optString("trial_type", ""),
            family = item.optString("family", ""),
            rowLabel = item.optString("row_label", ""),
            soaMs = item.optString("soa_ms", ""),
            noiseType = item.optString("noise_type", ""),
            durationS = item.optDouble("duration_s", 0.0).coerceAtLeast(0.0),
            tactileOnsetS = item.optNullableDouble("tactile_onset_s"),
            responseWindowOnsetS = item.optNullableDouble("response_window_onset_s"),
        )
    }
}

private fun JSONObject?.toMobileReconstructionContract(): MobileReconstructionContract {
    if (this == null) return MobileReconstructionContract.empty
    return MobileReconstructionContract(
        schema = optString("schema", ""),
        authority = optString("authority", ""),
        fallbackExecutionStrategy = optString("fallback_execution_strategy", ""),
        preferredLightweightStrategy = optString("preferred_lightweight_strategy", ""),
        sourceRunSetupSha256 = optString("source_run_setup_sha256", ""),
        scheduleHash = optString("schedule_hash", ""),
        buildingBlockCount = optInt("building_block_count", 0),
        blockCount = optInt("block_count", 0),
        trialCount = optInt("trial_count", 0),
    )
}

private fun JSONObject?.toMobileLslContract(): MobileLslContract {
    if (this == null) return MobileLslContract.empty
    val streamNames = optJSONObject("stream_names")
    return MobileLslContract(
        schema = optString("schema", ""),
        runtimeAuthority = optString("runtime_authority", ""),
        privacyDefault = optString("privacy_default", ""),
        richMarkersName = streamNames?.optString("rich_markers", "") ?: "",
        numericTriggersName = streamNames?.optString("numeric_triggers", "") ?: "",
        commandSignalsName = streamNames?.optString("command_signals", "") ?: "",
        commandAcksName = streamNames?.optString("command_acks", "") ?: "",
        nativeAndroidLslRequired = optBoolean("native_android_lsl_required", false),
        currentAndroidSourceBehavior = optString("current_android_source_behavior", ""),
        supportedCommands = optJSONArray("supported_commands").toStringList(),
    )
}

private fun JSONArray?.toMobileBlocks(): List<MobileBlock> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { index ->
        val item = optJSONObject(index) ?: return@mapNotNull null
        MobileBlock(
            blockId = item.optString("block_id", "block-${index + 1}"),
            index = item.optInt("index", index + 1),
            label = item.optString("label", "Block ${index + 1}"),
            durationS = item.optDouble("duration_s", 0.0).coerceAtLeast(0.0),
            trialCount = item.optInt("trial_count", 0),
            audioAssetId = item.optString("audio_asset_id", ""),
            trials = item.optJSONArray("trials").toMobileTrials(),
            tactileCues = item.optJSONArray("tactile_cues").toMobileCues(),
        )
    }.sortedBy { it.index }
}

private fun JSONArray?.toMobileTrials(): List<MobileTrial> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { index ->
        val item = optJSONObject(index) ?: return@mapNotNull null
        MobileTrial(
            trialNumber = item.optInt("trial_number", index + 1),
            trialUid = item.optString("trial_uid", ""),
            trialType = item.optString("trial_type", ""),
            family = item.optString("family", ""),
            soaMs = item.optString("soa_ms", ""),
            rowLabel = item.optString("row_label", ""),
            noiseType = item.optString("noise_type", ""),
            startS = item.optDouble("start_s", 0.0).coerceAtLeast(0.0),
            endS = item.optDouble("end_s", 0.0).coerceAtLeast(0.0),
            durationS = item.optDouble("duration_s", 0.0).coerceAtLeast(0.0),
            tactileOnsetS = item.optNullableDouble("tactile_onset_s"),
            responseWindowOnsetS = item.optNullableDouble("response_window_onset_s"),
            buildingBlockAssetId = item.optString("building_block_asset_id", ""),
        )
    }.sortedBy { it.startS }
}

private fun JSONArray?.toMobileCues(): List<MobileCue> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { index ->
        val item = optJSONObject(index) ?: return@mapNotNull null
        MobileCue(
            cueId = item.optInt("cue_id", index + 1),
            trialNumber = item.optInt("trial_number", 0),
            trialUid = item.optString("trial_uid", ""),
            timeS = item.optDouble("time_s", 0.0).coerceAtLeast(0.0),
            trialRelativeTimeS = item.optDouble("trial_relative_time_s", 0.0).coerceAtLeast(0.0),
            soaMs = item.optString("soa_ms", ""),
            rowLabel = item.optString("row_label", ""),
            noiseType = item.optString("noise_type", ""),
        )
    }.sortedBy { it.timeS }
}

private fun JSONArray?.toStringList(): List<String> {
    if (this == null) return emptyList()
    return (0 until length()).mapNotNull { index -> optString(index).takeIf { it.isNotBlank() } }
}

private fun JSONObject.optNullableDouble(key: String): Double? {
    if (!has(key) || isNull(key)) return null
    val value = optDouble(key, Double.NaN)
    return if (value.isFinite()) value.coerceAtLeast(0.0) else null
}
