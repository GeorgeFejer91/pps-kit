package io.ppskit.runnercompanion

import android.content.Context
import android.os.SystemClock
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

internal const val PHONE_CONTROLLER_COMMAND_ROW_SCHEMA = "pps-android-controller-command-row.v1"
internal const val PHONE_CONTROLLER_RUNTIME_STATUS_SCHEMA = "pps-android-controller-runtime-status.v1"

internal fun buildPhoneControllerCommandRow(
    pairing: PairingInfo,
    runPackage: MobileRunPackage?,
    summary: MobilePackageSummary?,
    command: String,
    commandId: String = "android-controller-${UUID.randomUUID()}",
    issuedLslTime: Double = 0.0,
    phoneUnixMs: Long = System.currentTimeMillis(),
    phoneElapsedRealtimeMs: Long = SystemClock.elapsedRealtime(),
): JSONObject {
    val targetSessionId = runPackage?.partSessionId?.ifBlank { runPackage.sessionId }
        ?: runPackage?.sessionId
        ?: pairing.sessionId
    val packageId = runPackage?.packageId ?: summary?.packageId.orEmpty()
    val participantId = runPackage?.participantId ?: summary?.participantId.orEmpty()
    val payload = JSONObject()
        .put("token", pairing.token)
        .put("package_id", packageId)
        .put("participant_id", participantId)
        .put("target_session_id", targetSessionId)
        .put("target_part_session_id", runPackage?.partSessionId.orEmpty())
        .put("target_session_group_id", runPackage?.sessionGroupId.orEmpty())
        .put("target_part_number", runPackage?.partNumber.orEmpty())
        .put("requested_by", "android_controller")
        .put("native_transport_available", false)
        .put("current_android_source_behavior", "local_controller_outbox_only")
        .put("timestamp_quality", "android_elapsed_realtime_not_lsl_local_clock")
    val signal = PhoneLslCommandSignal(
        commandId = commandId,
        sessionId = targetSessionId,
        senderId = "android_controller",
        command = command,
        issuedLslTime = issuedLslTime,
        payload = payload,
    )
    val sample = phoneCommandToSample(signal)
    return JSONObject()
        .put("schema", PHONE_CONTROLLER_COMMAND_ROW_SCHEMA)
        .put("command_id", commandId)
        .put("command", command)
        .put("package_id", packageId)
        .put("participant_id", participantId)
        .put("target_session_id", targetSessionId)
        .put("phone_unix_ms", phoneUnixMs)
        .put("phone_elapsed_realtime_ms", phoneElapsedRealtimeMs)
        .put("native_transport_available", false)
        .put("current_android_source_behavior", "local_controller_outbox_only")
        .put("command_channels", stringArray(PHONE_LSL_COMMAND_CHANNELS))
        .put("command_sample", stringArray(sample))
        .put("payload", payload)
}

internal fun writePhoneControllerCommandOutbox(
    context: Context,
    pairing: PairingInfo,
    runPackage: MobileRunPackage?,
    summary: MobilePackageSummary?,
    command: String,
): JSONObject {
    val dir = phoneControllerDir(context, pairing.sessionId)
    dir.mkdirs()
    val row = buildPhoneControllerCommandRow(
        pairing = pairing,
        runPackage = runPackage,
        summary = summary,
        command = command,
        issuedLslTime = SystemClock.elapsedRealtimeNanos() / 1_000_000_000.0,
    )
    val outbox = File(dir, "phone_controller_command_outbox.jsonl")
    outbox.appendText(row.toString() + "\n", Charsets.UTF_8)
    val status = phoneControllerRuntimeStatus(pairing, runPackage, summary)
    val statusFile = File(dir, "phone_controller_runtime_status.json")
    statusFile.writeText(status.toString(2), Charsets.UTF_8)
    return JSONObject()
        .put("schema", "pps-android-controller-command-write.v1")
        .put("status", "queued_local_outbox")
        .put("command", command)
        .put("command_id", row.optString("command_id"))
        .put("outbox_path", outbox.absolutePath)
        .put("runtime_status_path", statusFile.absolutePath)
        .put("native_transport_available", false)
}

internal fun phoneControllerRuntimeStatus(
    pairing: PairingInfo,
    runPackage: MobileRunPackage?,
    summary: MobilePackageSummary?,
): JSONObject {
    val supportedCommands = runPackage?.lsl?.supportedCommands?.takeIf { it.isNotEmpty() }
        ?: listOf("start_experiment", "pause", "resume", "continue_instruction", "request_snapshot", "operator_note")
    return JSONObject()
        .put("schema", PHONE_CONTROLLER_RUNTIME_STATUS_SCHEMA)
        .put("session_id", pairing.sessionId)
        .put("package_id", runPackage?.packageId ?: summary?.packageId.orEmpty())
        .put("participant_id", runPackage?.participantId ?: summary?.participantId.orEmpty())
        .put("role", "controller")
        .put("native_transport", "liblsl")
        .put("native_transport_available", false)
        .put("current_android_source_behavior", "local_controller_outbox_only")
        .put("reason", "native_liblsl_android_layer_not_present")
        .put(
            "streams",
            JSONObject()
                .put("command_signals", runPackage?.lsl?.commandSignalsName?.ifBlank { PHONE_LSL_COMMAND_STREAM_NAME } ?: PHONE_LSL_COMMAND_STREAM_NAME)
                .put("command_acks", runPackage?.lsl?.commandAcksName?.ifBlank { PHONE_LSL_ACK_STREAM_NAME } ?: PHONE_LSL_ACK_STREAM_NAME),
        )
        .put(
            "command_protocol",
            JSONObject()
                .put("command_schema", PHONE_LSL_COMMAND_SCHEMA)
                .put("ack_schema", PHONE_LSL_ACK_SCHEMA)
                .put("command_channels", stringArray(PHONE_LSL_COMMAND_CHANNELS))
                .put("ack_channels", stringArray(PHONE_LSL_ACK_CHANNELS))
                .put("supported_commands", stringArray(supportedCommands))
                .put("token_required", true),
        )
}

private fun phoneControllerDir(context: Context, sessionId: String): File =
    File(context.filesDir, "phone_controller/${safePhoneControllerName(sessionId)}")

private fun safePhoneControllerName(value: String): String =
    value.replace(Regex("[^A-Za-z0-9._-]+"), "-").trim('-', '.', '_').ifBlank { "session" }

private fun stringArray(values: List<String>): JSONArray =
    JSONArray().also { array -> values.forEach { array.put(it) } }
