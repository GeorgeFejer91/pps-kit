package io.ppskit.runnercompanion

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

internal const val PHONE_RUN_CATALOG_ENTRY_SCHEMA = "pps-android-phone-run-catalog-entry.v1"
internal const val PHONE_RUN_CATALOG_SCHEMA = "pps-android-phone-run-catalog.v1"
internal const val PHONE_RUN_CATALOG_WRITE_SCHEMA = "pps-android-phone-run-catalog-write.v1"
internal const val PHONE_OWNED_DATA_EXPORT_SCHEMA = "pps-android-phone-owned-data-export.v1"
private const val PHONE_OWNED_EXPORTS_ARCHIVE_ROOT = "phone_owned_exports"
internal val PHONE_DATA_MIN_FIELDNAMES = listOf(
    "participant_id",
    "session_id",
    "part_session_id",
    "part_number",
    "block_number",
    "block_label",
    "trial_number",
    "trial_number_global",
    "trial_uid",
    "condition",
    "phase",
    "noise_type",
    "trial_type",
    "soa_ms",
    "response_given",
    "hit_miss",
    "reaction_time_ms",
)

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
        .put("randomization_seed", runPackage.randomizationSeed)
        .put("participant_roster_count", runPackage.participantRoster.size)
        .put("source_segment_hashes", runPackage.sourceSegmentHashes.toJsonObject())
        .put("phone_owned_session", true)
        .put("completed", complete)
        .put("completion_reason", summary.optString("completion_reason", if (complete) "completed" else "in_progress"))
        .put("phone_run_dir", runDir.absolutePath)
        .put("artifact_file", artifactFile.name)
        .put("event_count", summary.optInt("total_event_count", 0))
        .put("command_diary_count", summary.optInt("command_diary_count", 0))
        .put("lsl_marker_mirror_count", summary.optInt("lsl_marker_mirror_count", 0))
        .put("native_lsl_pushed_count", summary.optInt("native_lsl_pushed_count", 0))
        .put("native_lsl_failed_count", summary.optInt("native_lsl_failed_count", 0))
        .put("native_lsl_rich_marker_pushed_count", summary.optInt("native_lsl_rich_marker_pushed_count", 0))
        .put("native_lsl_rich_marker_failed_count", summary.optInt("native_lsl_rich_marker_failed_count", 0))
        .put("native_lsl_numeric_trigger_pushed_count", summary.optInt("native_lsl_numeric_trigger_pushed_count", 0))
        .put("native_lsl_numeric_trigger_failed_count", summary.optInt("native_lsl_numeric_trigger_failed_count", 0))
        .put("native_lsl_command_received_count", summary.optInt("native_lsl_command_received_count", 0))
        .put("native_lsl_command_ack_count", summary.optInt("native_lsl_command_ack_count", 0))
        .put("native_lsl_command_ack_failed_count", summary.optInt("native_lsl_command_ack_failed_count", 0))
        .put("native_lsl_command_rejected_count", summary.optInt("native_lsl_command_rejected_count", 0))
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

internal fun writePhoneOwnedDataExport(
    filesDir: File,
    runPackage: MobileRunPackage,
    runDir: File,
    catalogEntry: JSONObject,
    responseLedgerRows: List<JSONObject>,
): JSONObject {
    val participantId = safePhoneRunCatalogName(
        runPackage.participantId.ifBlank { catalogEntry.optString("participant_id", "PXX") }.ifBlank { "PXX" },
    )
    val runId = safePhoneRunCatalogName(catalogEntry.optString("run_id", runDir.name).ifBlank { runDir.name })
    val exportRoot = File(filesDir, "phone_owned_exports")
    val dataMinDir = File(exportRoot, "1.Data_min")
    val dataMaxRunDir = File(File(File(exportRoot, "2.Data_max"), participantId), "runs/$runId")
    dataMinDir.mkdirs()

    val rows = buildPhoneDataMinRows(runPackage, responseLedgerRows)
    val participantCsv = File(dataMinDir, "$participantId.csv")
    writePhoneDataMinCsv(participantCsv, rows)
    val masterCsv = refreshPhoneDataMinMaster(dataMinDir)
    val dataMaxRunArchivePath = "$PHONE_OWNED_EXPORTS_ARCHIVE_ROOT/2.Data_max/$participantId/runs/$runId"
    val exportFile = File(runDir, "phone_owned_data_export.json")

    val export = JSONObject()
        .put("schema", PHONE_OWNED_DATA_EXPORT_SCHEMA)
        .put("participant_id", participantId)
        .put("run_id", runId)
        .put("package_id", runPackage.packageId)
        .put("session_id", runPackage.sessionId)
        .put("part_session_id", runPackage.partSessionId)
        .put("part_number", runPackage.partNumber)
        .put("phone_owned_session", true)
        .put("data_min_schema", "pps-data-min-publication-trials.v1")
        .put("data_min_fieldnames", JSONArray().also { array -> PHONE_DATA_MIN_FIELDNAMES.forEach { array.put(it) } })
        .put("data_min_participant_csv", participantCsv.absolutePath)
        .put("data_min_master_successful_participants_csv", masterCsv.absolutePath)
        .put("data_min_row_count", rows.size)
        .put("data_max_run_dir", dataMaxRunDir.absolutePath)
        .put("data_max_source_run_dir", runDir.absolutePath)
        .put("artifact_path", exportFile.absolutePath)
        .put(
            "portable_paths",
            JSONObject()
                .put("archive_run_root", ".")
                .put("phone_owned_data_export", exportFile.name)
                .put("phone_owned_exports_root", PHONE_OWNED_EXPORTS_ARCHIVE_ROOT)
                .put("data_min_participant_csv", "$PHONE_OWNED_EXPORTS_ARCHIVE_ROOT/1.Data_min/${participantCsv.name}")
                .put("data_min_master_successful_participants_csv", "$PHONE_OWNED_EXPORTS_ARCHIVE_ROOT/1.Data_min/${masterCsv.name}")
                .put("data_max_run_dir", dataMaxRunArchivePath)
                .put("data_max_completion_json", "$dataMaxRunArchivePath/completion.json")
                .put("data_max_phone_owned_data_export", "$dataMaxRunArchivePath/${exportFile.name}")
                .put("data_max_artifact_file_inventory", "$dataMaxRunArchivePath/artifact_file_inventory.json")
                .put("data_max_artifact_file_inventory_csv", "$dataMaxRunArchivePath/artifact_file_inventory.csv"),
        )
        .put("privacy", JSONObject()
            .put("scope", "app_private_phone_owned_export")
            .put("demographics_in_stream_name", false)
            .put("participant_names_exported", false))

    exportFile.writeText(export.toString(2), Charsets.UTF_8)
    dataMaxRunDir.deleteRecursively()
    dataMaxRunDir.parentFile?.mkdirs()
    runDir.copyRecursively(dataMaxRunDir, overwrite = true)
    return export
}

internal fun buildPhoneDataMinRows(
    runPackage: MobileRunPackage,
    responseLedgerRows: List<JSONObject>,
): List<Map<String, String>> {
    val trialLookup = mutableMapOf<String, Pair<MobileBlock, MobileTrial>>()
    runPackage.blocks.forEach { block ->
        block.trials.forEach { trial ->
            if (trial.trialUid.isNotBlank()) trialLookup[trial.trialUid] = block to trial
        }
    }
    var globalIndex = 1
    return responseLedgerRows
        .filter { row ->
            val role = row.optString("ledger_role", "source_trial")
            role == "source_trial" || role == "topup_rescue"
        }
        .map { row ->
            val role = row.optString("ledger_role", "source_trial")
            val sourceTrialUid = if (role == "topup_rescue") {
                row.optString("source_trial_uid", "")
            } else {
                row.optString("trial_uid", "")
            }
            val source = trialLookup[sourceTrialUid]
            val block = source?.first
            val trial = source?.second
            val hit = row.optBoolean("hit", false)
            val trialType = trial?.trialType.orEmpty()
            val trialFamily = trial?.family.orEmpty()
            val condition = trialFamily.ifBlank { trialType }
            val blockNumber = if (role == "topup_rescue") {
                (runPackage.blocks.maxOfOrNull { it.index } ?: 0) + 1
            } else {
                row.optInt("block_index", block?.index ?: 0)
            }
            mapOf(
                "participant_id" to runPackage.participantId,
                "session_id" to runPackage.sessionId,
                "part_session_id" to runPackage.partSessionId,
                "part_number" to runPackage.partNumber,
                "block_number" to blockNumber.toString(),
                "block_label" to if (role == "topup_rescue") "Phone top-up" else (block?.label ?: row.optString("block_id", "")),
                "trial_number" to row.optString("trial_number", trial?.trialNumber?.toString() ?: ""),
                "trial_number_global" to (globalIndex++).toString(),
                "trial_uid" to row.optString("trial_uid", ""),
                "condition" to condition,
                "phase" to normalizePhoneDataMinPhase(trial?.rowLabel ?: ""),
                "noise_type" to (trial?.noiseType ?: ""),
                "trial_type" to trialType,
                "soa_ms" to (trial?.soaMs ?: ""),
                "response_given" to hit.toString(),
                "hit_miss" to if (hit) "Hit" else "Miss",
                "reaction_time_ms" to row.optString("rt_ms", ""),
            )
        }
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

private fun writePhoneDataMinCsv(path: File, rows: List<Map<String, String>>) {
    path.parentFile?.mkdirs()
    path.writeText(
        buildString {
            append(PHONE_DATA_MIN_FIELDNAMES.joinToString(","))
            append("\n")
            rows.forEach { row ->
                append(PHONE_DATA_MIN_FIELDNAMES.joinToString(",") { field -> phoneCsvCell(row[field].orEmpty()) })
                append("\n")
            }
        },
        Charsets.UTF_8,
    )
}

private fun refreshPhoneDataMinMaster(dataMinDir: File): File {
    val master = File(dataMinDir, "master_successful_participants.csv")
    val participantCsvs = dataMinDir.listFiles()
        ?.filter { it.isFile && it.name.endsWith(".csv") && it.name != master.name }
        ?.sortedBy { it.name.lowercase() }
        ?: emptyList()
    master.writeText(
        buildString {
            append(PHONE_DATA_MIN_FIELDNAMES.joinToString(","))
            append("\n")
            participantCsvs.forEach { csv ->
                csv.readLines(Charsets.UTF_8)
                    .drop(1)
                    .filter { it.isNotBlank() }
                    .forEach { line ->
                        append(line)
                        append("\n")
                    }
            }
        },
        Charsets.UTF_8,
    )
    return master
}

private fun normalizePhoneDataMinPhase(value: String): String =
    when (value.trim().lowercase()) {
        "inhale", "inhalation", "inspiration" -> "Inhale"
        "exhale", "exhalation", "expiration" -> "Exhale"
        else -> value
    }

private fun phoneCsvCell(value: String): String =
    if (value.any { it == ',' || it == '"' || it == '\n' || it == '\r' }) {
        "\"${value.replace("\"", "\"\"")}\""
    } else {
        value
    }
