package io.ppskit.runnercompanion

import org.json.JSONArray
import org.json.JSONObject

const val MOBILE_PACKAGE_LIST_SCHEMA = "pps-mobile-run-package-list.v1"
const val MOBILE_PACKAGE_SCHEMA = "pps-mobile-run-package.v1"

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
    val title: String,
    val blocks: List<MobileBlock>,
    val assets: List<MobileAsset>,
    val mobileRunnable: Boolean,
    val phoneOwnedSession: Boolean,
    val warnings: List<String>,
) {
    fun asset(assetId: String): MobileAsset? = assets.firstOrNull { it.assetId == assetId }
}

data class MobileAsset(
    val assetId: String,
    val filename: String,
    val mediaType: String,
    val sizeBytes: Long,
    val sha256: String,
    val available: Boolean,
)

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
        require(root.optString("schema") == MOBILE_PACKAGE_LIST_SCHEMA) { "Unsupported mobile package list schema." }
        return MobilePackageList(
            activePackageId = root.optString("active_package_id", ""),
            packages = root.optJSONArray("packages").toPackageSummaries(),
        )
    }

    fun parseManifest(raw: String): MobileRunPackage {
        val root = JSONObject(raw)
        require(root.optString("schema") == MOBILE_PACKAGE_SCHEMA) { "Unsupported mobile package schema." }
        return MobileRunPackage(
            packageId = root.optString("package_id", ""),
            participantId = root.optString("participant_id", ""),
            sessionId = root.optString("session_id", ""),
            title = root.optString("title", ""),
            blocks = root.optJSONArray("blocks").toMobileBlocks(),
            assets = root.optJSONArray("assets").toMobileAssets(),
            mobileRunnable = root.optBoolean("mobile_runnable", false),
            phoneOwnedSession = root.optBoolean("phone_owned_session", false),
            warnings = root.optJSONArray("warnings").toStringList(),
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
            sizeBytes = item.optLong("size_bytes", 0L),
            sha256 = item.optString("sha256", ""),
            available = item.optBoolean("available", true),
        )
    }
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
