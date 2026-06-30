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
    commandPayload: JSONObject = JSONObject(),
    commandId: String = "android-controller-${UUID.randomUUID()}",
    issuedLslTime: Double = 0.0,
    phoneUnixMs: Long = System.currentTimeMillis(),
    phoneElapsedRealtimeMs: Long = SystemClock.elapsedRealtime(),
    nativeTransportAvailable: Boolean = false,
    nativeControllerTransportEnabled: Boolean = false,
    currentAndroidSourceBehavior: String = "local_controller_outbox_only",
    timestampQuality: String = "android_elapsed_realtime_not_lsl_local_clock",
): JSONObject {
    val target = resolvePhoneControllerTarget(pairing, runPackage, summary)
    val payload = JSONObject(commandPayload.toString())
        .put("token", pairing.token)
        .put("package_id", target.packageId)
        .put("participant_id", target.participantId)
        .put("target_session_id", target.sessionId)
        .put("target_part_session_id", target.partSessionId)
        .put("target_session_group_id", target.sessionGroupId)
        .put("target_part_number", target.partNumber)
        .put("requested_by", "android_controller")
        .put("native_transport_available", nativeTransportAvailable)
        .put("native_controller_transport_enabled", nativeControllerTransportEnabled)
        .put("current_android_source_behavior", currentAndroidSourceBehavior)
        .put("timestamp_quality", timestampQuality)
    val signal = PhoneLslCommandSignal(
        commandId = commandId,
        sessionId = target.sessionId,
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
        .put("package_id", target.packageId)
        .put("participant_id", target.participantId)
        .put("target_session_id", target.sessionId)
        .put("phone_unix_ms", phoneUnixMs)
        .put("phone_elapsed_realtime_ms", phoneElapsedRealtimeMs)
        .put("native_transport_available", nativeTransportAvailable)
        .put("native_controller_transport_enabled", nativeControllerTransportEnabled)
        .put("native_lsl_sent", false)
        .put("current_android_source_behavior", currentAndroidSourceBehavior)
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
    commandPayload: JSONObject = JSONObject(),
    nativeBridgeStatus: PhoneNativeLslBridgeStatus = PhoneNativeLslBridgeFactory.create().status(),
    controllerTransport: PhoneLslControllerTransport? = null,
): JSONObject {
    val dir = phoneControllerDir(context, pairing.sessionId)
    dir.mkdirs()
    val nativeEnabled = controllerTransport?.status?.enabled == true
    val sourceBehavior = if (nativeEnabled) "native_lsl_controller_with_local_outbox" else "local_controller_outbox_only"
    val timestampQuality = if (nativeEnabled) "lsl_local_clock" else "android_elapsed_realtime_not_lsl_local_clock"
    val row = buildPhoneControllerCommandRow(
        pairing = pairing,
        runPackage = runPackage,
        summary = summary,
        command = command,
        commandPayload = commandPayload,
        issuedLslTime = controllerTransport?.takeIf { nativeEnabled }?.localClock()
            ?: (SystemClock.elapsedRealtimeNanos() / 1_000_000_000.0),
        nativeTransportAvailable = nativeBridgeStatus.available,
        nativeControllerTransportEnabled = nativeEnabled,
        currentAndroidSourceBehavior = sourceBehavior,
        timestampQuality = timestampQuality,
    )
    val sampleJson = row.getJSONArray("command_sample")
    val signal = phoneCommandFromSample((0 until sampleJson.length()).map { sampleJson.getString(it) })
    val nativeSent = controllerTransport?.takeIf { nativeEnabled }?.sendCommand(signal) == true
    row.put("native_lsl_sent", nativeSent)
    val ack = if (nativeSent) waitForControllerAck(controllerTransport, signal.commandId) else null
    if (ack != null) {
        row
            .put("ack_received", true)
            .put("ack_status", ack.status)
            .put("ack_reason", ack.reason)
            .put("ack_channels", stringArray(PHONE_LSL_ACK_CHANNELS))
            .put("ack_sample", stringArray(phoneAckToSample(ack)))
    } else {
        row.put("ack_received", false)
    }
    val outbox = File(dir, "phone_controller_command_outbox.jsonl")
    outbox.appendText(row.toString() + "\n", Charsets.UTF_8)
    val status = phoneControllerRuntimeStatus(
        pairing = pairing,
        runPackage = runPackage,
        summary = summary,
        nativeBridgeStatus = nativeBridgeStatus,
        controllerTransportStatus = controllerTransport?.status,
    )
    val statusFile = File(dir, "phone_controller_runtime_status.json")
    statusFile.writeText(status.toString(2), Charsets.UTF_8)
    return JSONObject()
        .put("schema", "pps-android-controller-command-write.v1")
        .put("status", if (nativeSent) "sent_native_lsl_and_queued_outbox" else "queued_local_outbox")
        .put("command", command)
        .put("command_id", row.optString("command_id"))
        .put("outbox_path", outbox.absolutePath)
        .put("runtime_status_path", statusFile.absolutePath)
        .put("native_transport_available", nativeBridgeStatus.available)
        .put("native_controller_transport_enabled", nativeEnabled)
        .put("native_lsl_sent", nativeSent)
        .put("ack_received", ack != null)
        .put("ack_status", ack?.status ?: "")
}

internal fun phoneControllerRuntimeStatus(
    pairing: PairingInfo,
    runPackage: MobileRunPackage?,
    summary: MobilePackageSummary?,
    nativeBridgeStatus: PhoneNativeLslBridgeStatus = PhoneNativeLslBridgeFactory.create().status(),
    controllerTransportStatus: PhoneNativeLslBridgeStatus? = null,
): JSONObject {
    val supportedCommands = runPackage?.lsl?.supportedCommands?.takeIf { it.isNotEmpty() }
        ?: listOf("start_experiment", "pause", "resume", "continue_instruction", "stop_after_block", "request_snapshot", "operator_note")
    val controllerEnabled = controllerTransportStatus?.enabled == true
    return JSONObject()
        .put("schema", PHONE_CONTROLLER_RUNTIME_STATUS_SCHEMA)
        .put("session_id", pairing.sessionId)
        .put("package_id", runPackage?.packageId ?: summary?.packageId.orEmpty())
        .put("participant_id", runPackage?.participantId ?: summary?.participantId.orEmpty())
        .put("role", "controller")
        .put("native_transport", "liblsl")
        .put("native_transport_available", nativeBridgeStatus.available)
        .put("native_controller_transport_enabled", controllerEnabled)
        .put("current_android_source_behavior", if (controllerEnabled) "native_lsl_controller_with_local_outbox" else "local_controller_outbox_only")
        .put("reason", if (controllerEnabled) "" else controllerTransportStatus?.reason?.ifBlank { nativeBridgeStatus.reason } ?: nativeBridgeStatus.reason.ifBlank { "native_lsl_controller_transport_not_enabled" })
        .put("native_bridge", phoneNativeLslStatusJson(nativeBridgeStatus, controllerTransportStatus = controllerTransportStatus))
        .put(
            "streams",
            JSONObject()
                .put("command_signals", runPackage?.lsl?.commandSignalsName?.ifBlank { PHONE_LSL_COMMAND_STREAM_NAME } ?: PHONE_LSL_COMMAND_STREAM_NAME)
                .put("command_acks", runPackage?.lsl?.commandAcksName?.ifBlank { PHONE_LSL_ACK_STREAM_NAME } ?: PHONE_LSL_ACK_STREAM_NAME),
        )
        .put("stream_descriptions", phoneControllerLslStreamDescriptions(pairing, runPackage, summary))
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

internal fun phoneControllerLslStreamDescriptions(
    pairing: PairingInfo,
    runPackage: MobileRunPackage?,
    summary: MobilePackageSummary?,
): JSONObject {
    val target = resolvePhoneControllerTarget(pairing, runPackage, summary)
    val commandName = runPackage?.lsl?.commandSignalsName?.ifBlank { PHONE_LSL_COMMAND_STREAM_NAME }
        ?: PHONE_LSL_COMMAND_STREAM_NAME
    val ackName = runPackage?.lsl?.commandAcksName?.ifBlank { PHONE_LSL_ACK_STREAM_NAME }
        ?: PHONE_LSL_ACK_STREAM_NAME
    val privacyDefault = runPackage?.lsl?.privacyDefault?.ifBlank { "metadata_payload_only" }
        ?: "metadata_payload_only"
    val sessionToken = safePhoneControllerName(target.sessionId)
    val controllerToken = safePhoneControllerName("android_controller")
    return JSONObject()
        .put("schema", "pps-android-lsl-stream-descriptions.v1")
        .put("runtime_authority", "android_controller")
        .put("role", "controller")
        .put("target_session_id", target.sessionId)
        .put("participant_id", target.participantId)
        .put(
            "privacy",
            JSONObject()
                .put("default", privacyDefault)
                .put("demographics_in_stream_name", false)
                .put("participant_demographics_location", "metadata_and_payload_artifacts"),
        )
        .put(
            "command_signals",
            JSONObject()
                .put("name", commandName)
                .put("type", "CommandSignals")
                .put("role", "outlet")
                .put("channel_format", "string")
                .put("channel_count", PHONE_LSL_COMMAND_CHANNELS.size)
                .put("nominal_srate_hz", 0.0)
                .put("source_id", "pps-android-controller-signals-v1-$sessionToken-$controllerToken")
                .put("channel_labels", stringArray(PHONE_LSL_COMMAND_CHANNELS))
                .put("token_required", true),
        )
        .put(
            "command_acks",
            JSONObject()
                .put("name", ackName)
                .put("type", "CommandAcks")
                .put("role", "inlet")
                .put("channel_format", "string")
                .put("channel_count", PHONE_LSL_ACK_CHANNELS.size)
                .put("nominal_srate_hz", 0.0)
                .put("source_id_pattern", "pps-*-command-acks-v1-*")
                .put("channel_labels", stringArray(PHONE_LSL_ACK_CHANNELS)),
        )
}

private data class PhoneControllerTarget(
    val sessionId: String,
    val packageId: String,
    val participantId: String,
    val partSessionId: String,
    val sessionGroupId: String,
    val partNumber: String,
)

private fun resolvePhoneControllerTarget(
    pairing: PairingInfo,
    runPackage: MobileRunPackage?,
    summary: MobilePackageSummary?,
): PhoneControllerTarget {
    if (runPackage != null) {
        return PhoneControllerTarget(
            sessionId = runPackage.partSessionId.ifBlank { runPackage.sessionId }.ifBlank { pairing.sessionId },
            packageId = runPackage.packageId,
            participantId = runPackage.participantId,
            partSessionId = runPackage.partSessionId,
            sessionGroupId = runPackage.sessionGroupId,
            partNumber = runPackage.partNumber,
        )
    }
    if (summary != null) {
        return PhoneControllerTarget(
            sessionId = summary.partSessionId.ifBlank { summary.sessionId }.ifBlank { pairing.sessionId },
            packageId = summary.packageId,
            participantId = summary.participantId,
            partSessionId = summary.partSessionId,
            sessionGroupId = summary.sessionGroupId,
            partNumber = summary.partNumber,
        )
    }
    return PhoneControllerTarget(
        sessionId = pairing.sessionId,
        packageId = "",
        participantId = "",
        partSessionId = "",
        sessionGroupId = "",
        partNumber = "",
    )
}

private fun waitForControllerAck(transport: PhoneLslControllerTransport, commandId: String): PhoneLslCommandAck? {
    repeat(6) {
        val sample = transport.pullAckSample(timeoutS = 0.05) ?: return@repeat
        val ack = runCatching { phoneAckFromSample(sample.sample) }.getOrNull() ?: return@repeat
        if (ack.commandId == commandId) return ack
    }
    return null
}

private fun phoneControllerDir(context: Context, sessionId: String): File =
    File(context.filesDir, "phone_controller/${safePhoneControllerName(sessionId)}")

private fun safePhoneControllerName(value: String): String =
    value.replace(Regex("[^A-Za-z0-9._-]+"), "-").trim('-', '.', '_').ifBlank { "session" }

private fun stringArray(values: List<String>): JSONArray =
    JSONArray().also { array -> values.forEach { array.put(it) } }
