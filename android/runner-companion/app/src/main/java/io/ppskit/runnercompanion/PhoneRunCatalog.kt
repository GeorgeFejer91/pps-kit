package io.ppskit.runnercompanion

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

internal const val PHONE_RUN_CATALOG_ENTRY_SCHEMA = "pps-android-phone-run-catalog-entry.v1"
internal const val PHONE_RUN_CATALOG_SCHEMA = "pps-android-phone-run-catalog.v1"
internal const val PHONE_RUN_CATALOG_WRITE_SCHEMA = "pps-android-phone-run-catalog-write.v1"

internal fun buildPhoneRunCatalogEntry(
    runPackage: MobileRunPackage,
    runId: String,
    runDir: File,
    artifactFile: File,
    complete: Boolean,
    participantMetadata: JSONObject,
    lslRuntimeStatus: JSONObject,
    summary: JSONObject,
): JSONObject {
    val now = System.currentTimeMillis()
    val participantSummary = JSONObject()
        .put("participant_id", participantMetadata.optString("participant_id", runPackage.participantId))
        .put("age_years", participantMetadata.optString("age_years", ""))
        .put("handedness", participantMetadata.optString("handedness", ""))
        .put("gender", participantMetadata.optString("gender", ""))
        .put("tactile_threshold_percent", participantMetadata.opt("tactile_threshold_percent") ?: JSONObject.NULL)
        .put("tactile_threshold_source", participantMetadata.optString("tactile_threshold_source", ""))
    return JSONObject()
        .put("schema", PHONE_RUN_CATALOG_ENTRY_SCHEMA)
        .put("updated_unix_ms", now)
        .put("run_id", runId)
        .put("package_id", runPackage.packageId)
        .put("participant_id", runPackage.participantId)
        .put("session_id", runPackage.sessionId)
        .put("session_group_id", runPackage.sessionGroupId)
        .put("part_session_id", runPackage.partSessionId)
        .put("part_number", runPackage.partNumber)
        .put("title", runPackage.title)
        .put("asset_strategy", mobilePackageAssetStrategy(runPackage))
        .put("phone_owned_session", true)
        .put("completed", complete)
        .put("completion_reason", summary.optString("completion_reason", if (complete) "completed" else "in_progress"))
        .put("phone_run_dir", runDir.absolutePath)
        .put("artifact_file", artifactFile.name)
        .put("event_count", summary.optInt("total_event_count", 0))
        .put("command_diary_count", summary.optInt("command_diary_count", 0))
        .put("lsl_marker_mirror_count", summary.optInt("lsl_marker_mirror_count", 0))
        .put("native_lsl_transport_available", lslRuntimeStatus.optBoolean("native_transport_available", false))
        .put("native_lsl_marker_transport_enabled", lslRuntimeStatus.optBoolean("native_marker_transport_enabled", false))
        .put("native_lsl_command_receiver_available", lslRuntimeStatus.optBoolean("command_receiver_available", false))
        .put("participant_metadata_summary", participantSummary)
        .put("privacy", JSONObject().put("scope", "app_private_local_catalog").put("demographics_in_stream_name", false))
        .put("reconstruction", JSONObject()
            .put("package_asset_strategy", runPackage.reconstruction.packageAssetStrategy)
            .put("schedule_hash", runPackage.reconstruction.scheduleHash)
            .put("building_block_count", runPackage.buildingBlocks.size)
            .put("block_count", runPackage.blocks.size)
            .put("trial_count", runPackage.blocks.sumOf { it.trialCount }))
}

internal fun writePhoneRunCatalog(filesDir: File, runDir: File, entry: JSONObject): JSONObject {
    val root = File(filesDir, "phone_run_catalog")
    val participantId = entry.optString("participant_id", "PXX").ifBlank { "PXX" }
    val participantDir = File(root, safePhoneRunCatalogName(participantId))
    val entryFile = File(runDir, "phone_run_catalog_entry.json")
    val participantRunsFile = File(participantDir, "runs.jsonl")
    val participantLatestFile = File(participantDir, "latest_run.json")
    root.mkdirs()
    participantDir.mkdirs()
    runDir.mkdirs()

    val entryCopy = JSONObject(entry.toString())
    entryFile.writeText(entryCopy.toString(2), Charsets.UTF_8)
    upsertCatalogJsonl(participantRunsFile, entryCopy)
    participantLatestFile.writeText(entryCopy.toString(2), Charsets.UTF_8)
    val index = rebuildPhoneRunCatalogIndex(root)
    val indexFile = File(root, "index.json")
    indexFile.writeText(index.toString(2), Charsets.UTF_8)

    return JSONObject()
        .put("schema", PHONE_RUN_CATALOG_WRITE_SCHEMA)
        .put("entry_path", entryFile.absolutePath)
        .put("participant_runs_path", participantRunsFile.absolutePath)
        .put("participant_latest_path", participantLatestFile.absolutePath)
        .put("index_path", indexFile.absolutePath)
        .put("entry", entryCopy)
}

private fun upsertCatalogJsonl(path: File, entry: JSONObject) {
    val runId = entry.optString("run_id")
    val rows = mutableListOf<JSONObject>()
    var replaced = false
    if (path.isFile) {
        path.readLines(Charsets.UTF_8)
            .filter { it.isNotBlank() }
            .forEach { line ->
                val parsed = runCatching { JSONObject(line) }.getOrNull() ?: return@forEach
                if (parsed.optString("run_id") == runId) {
                    rows.add(JSONObject(entry.toString()))
                    replaced = true
                } else {
                    rows.add(parsed)
                }
            }
    }
    if (!replaced) rows.add(JSONObject(entry.toString()))
    path.parentFile?.mkdirs()
    path.writeText(rows.joinToString(separator = "\n", postfix = "\n") { it.toString() }, Charsets.UTF_8)
}

private fun rebuildPhoneRunCatalogIndex(root: File): JSONObject {
    val participants = JSONArray()
    var runCount = 0
    root.listFiles()?.filter { it.isDirectory }?.sortedBy { it.name }?.forEach { dir ->
        val runsFile = File(dir, "runs.jsonl")
        val rows = if (runsFile.isFile) {
            runsFile.readLines(Charsets.UTF_8)
                .filter { it.isNotBlank() }
                .mapNotNull { line -> runCatching { JSONObject(line) }.getOrNull() }
        } else {
            emptyList()
        }
        if (rows.isEmpty()) return@forEach
        val latest = rows.maxByOrNull { it.optLong("updated_unix_ms", 0L) } ?: rows.last()
        runCount += rows.size
        participants.put(JSONObject()
            .put("participant_id", latest.optString("participant_id", dir.name))
            .put("participant_dir", dir.name)
            .put("run_count", rows.size)
            .put("latest_run_id", latest.optString("run_id", ""))
            .put("latest_completed", latest.optBoolean("completed", false))
            .put("latest_updated_unix_ms", latest.optLong("updated_unix_ms", 0L)))
    }
    return JSONObject()
        .put("schema", PHONE_RUN_CATALOG_SCHEMA)
        .put("updated_unix_ms", System.currentTimeMillis())
        .put("participant_count", participants.length())
        .put("run_count", runCount)
        .put("participants", participants)
}

internal fun safePhoneRunCatalogName(value: String): String =
    value.replace(Regex("[^A-Za-z0-9._-]+"), "-").trim('-', '.', '_').ifBlank { "participant" }
