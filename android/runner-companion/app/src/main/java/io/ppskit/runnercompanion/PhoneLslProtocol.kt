package io.ppskit.runnercompanion

import org.json.JSONArray
import org.json.JSONObject

internal const val PHONE_LSL_RUNTIME_STATUS_SCHEMA = "pps-android-lsl-runtime-status.v1"
internal const val PHONE_LSL_MARKER_VERSION = "2.0"
internal const val PHONE_LSL_RICH_MARKER_STREAM_NAME = "PPSMarkersV2"
internal const val PHONE_LSL_NUMERIC_TRIGGER_STREAM_NAME = "PPSTriggerCodes"
internal const val PHONE_LSL_COMMAND_SCHEMA = "pps-lsl-command.v1"
internal const val PHONE_LSL_ACK_SCHEMA = "pps-lsl-command-ack.v1"
internal const val PHONE_LSL_COMMAND_STREAM_NAME = "PPSCommandSignalsV1"
internal const val PHONE_LSL_ACK_STREAM_NAME = "PPSCommandAcksV1"

internal val PHONE_LSL_MARKER_CHANNELS = listOf(
    "marker_version",
    "event_id",
    "event_type",
    "event_code",
    "trigger_key",
    "marker_name",
    "session_id",
    "participant_id",
    "session_group_id",
    "part_session_id",
    "part_number",
    "block_index",
    "trial_uid",
    "sample_index",
    "timestamp_quality",
    "payload_json",
)

internal val PHONE_LSL_COMMAND_CHANNELS = listOf(
    "schema",
    "command_id",
    "session_id",
    "sender_id",
    "command",
    "issued_lsl_time",
    "payload_json",
)

internal fun phoneMarkerToRichSample(marker: JSONObject): List<String> =
    listOf(
        marker.optString("marker_version", PHONE_LSL_MARKER_VERSION),
        marker.optString("event_id", ""),
        marker.optString("event_type", ""),
        marker.optString("event_code", ""),
        marker.optString("trigger_key", ""),
        marker.optString("marker_name", ""),
        marker.optString("session_id", ""),
        marker.optString("participant_id", ""),
        marker.optString("session_group_id", ""),
        marker.optString("part_session_id", ""),
        marker.optString("part_number", ""),
        marker.optString("block_index", ""),
        marker.optString("trial_uid", ""),
        marker.optString("sample_index", ""),
        marker.optString("timestamp_quality", ""),
        marker.optString("payload_json", "{}"),
    )

internal fun phoneMarkerTriggerCode(marker: JSONObject): Int =
    marker.optInt("event_code", 0)

internal val PHONE_LSL_ACK_CHANNELS = listOf(
    "schema",
    "command_id",
    "session_id",
    "receiver_id",
    "status",
    "reason",
    "received_lsl_time",
    "applied_lsl_time",
    "ack_lsl_time",
    "payload_json",
)

private val DEFAULT_PHONE_LSL_SUPPORTED_COMMANDS = listOf(
    "start_experiment",
    "start_part",
    "pause",
    "resume",
    "continue_instruction",
    "stop_after_block",
    "request_snapshot",
    "operator_note",
)

internal data class PhoneLslCommandSignal(
    val commandId: String,
    val sessionId: String,
    val senderId: String,
    val command: String,
    val issuedLslTime: Double,
    val payload: JSONObject = JSONObject(),
)

internal data class PhoneLslCommandApplicationResult(
    val status: String = "applied",
    val reason: String = "",
    val payload: JSONObject = JSONObject(),
)

internal data class PhoneLslCommandAck(
    val commandId: String,
    val sessionId: String,
    val receiverId: String,
    val status: String,
    val reason: String,
    val receivedLslTime: Double,
    val appliedLslTime: Double,
    val ackLslTime: Double,
    val payload: JSONObject = JSONObject(),
)

internal fun phoneCommandToSample(signal: PhoneLslCommandSignal): List<String> =
    listOf(
        PHONE_LSL_COMMAND_SCHEMA,
        signal.commandId,
        signal.sessionId,
        signal.senderId,
        signal.command,
        "%.9f".format(java.util.Locale.US, signal.issuedLslTime),
        JSONObject(signal.payload.toString()).toString(),
    )

internal fun phoneCommandFromSample(sample: List<Any?>): PhoneLslCommandSignal {
    val values = sample.map { it?.toString() ?: "" }
    require(values.size == PHONE_LSL_COMMAND_CHANNELS.size && values[0] == PHONE_LSL_COMMAND_SCHEMA) {
        "Unsupported LSL command sample schema."
    }
    return PhoneLslCommandSignal(
        commandId = values[1],
        sessionId = values[2],
        senderId = values[3],
        command = values[4],
        issuedLslTime = values[5].toDoubleOrNull() ?: 0.0,
        payload = jsonObjectFromString(values[6]),
    )
}

internal fun phoneAckToSample(ack: PhoneLslCommandAck): List<String> =
    listOf(
        PHONE_LSL_ACK_SCHEMA,
        ack.commandId,
        ack.sessionId,
        ack.receiverId,
        ack.status,
        ack.reason,
        "%.9f".format(java.util.Locale.US, ack.receivedLslTime),
        "%.9f".format(java.util.Locale.US, ack.appliedLslTime),
        "%.9f".format(java.util.Locale.US, ack.ackLslTime),
        JSONObject(ack.payload.toString()).toString(),
    )

internal fun phoneAckFromSample(sample: List<Any?>): PhoneLslCommandAck {
    val values = sample.map { it?.toString() ?: "" }
    require(values.size == PHONE_LSL_ACK_CHANNELS.size && values[0] == PHONE_LSL_ACK_SCHEMA) {
        "Unsupported LSL command ack sample schema."
    }
    return PhoneLslCommandAck(
        commandId = values[1],
        sessionId = values[2],
        receiverId = values[3],
        status = values[4],
        reason = values[5],
        receivedLslTime = values[6].toDoubleOrNull() ?: 0.0,
        appliedLslTime = values[7].toDoubleOrNull() ?: 0.0,
        ackLslTime = values[8].toDoubleOrNull() ?: 0.0,
        payload = jsonObjectFromString(values[9]),
    )
}

internal fun phoneLslRuntimeStatus(
    runPackage: MobileRunPackage,
    runId: String,
    nativeBridgeStatus: PhoneNativeLslBridgeStatus = PhoneNativeLslBridgeFactory.create().status(),
    markerTransportStatus: PhoneNativeLslBridgeStatus? = null,
    commandTransportStatus: PhoneNativeLslBridgeStatus? = null,
    commandReceiverAvailable: Boolean = false,
): JSONObject {
    val richName = runPackage.lsl.richMarkersName.ifBlank { "PPSMarkersV2" }
    val numericName = runPackage.lsl.numericTriggersName.ifBlank { "PPSTriggerCodes" }
    val commandName = runPackage.lsl.commandSignalsName.ifBlank { PHONE_LSL_COMMAND_STREAM_NAME }
    val ackName = runPackage.lsl.commandAcksName.ifBlank { PHONE_LSL_ACK_STREAM_NAME }
    val activeMarkerTransport = markerTransportStatus?.enabled == true
    val activeCommandTransport = commandTransportStatus?.enabled == true || commandReceiverAvailable
    val nativeAvailable = nativeBridgeStatus.available
    val reason = when {
        !nativeAvailable -> nativeBridgeStatus.reason
        markerTransportStatus != null && !activeMarkerTransport -> markerTransportStatus.reason
        commandTransportStatus != null && !activeCommandTransport -> commandTransportStatus.reason
        else -> nativeBridgeStatus.reason
    }
    val sourceBehavior = when {
        activeMarkerTransport && activeCommandTransport -> "native_lsl_markers_and_commands_with_local_mirror"
        activeMarkerTransport -> "native_lsl_markers_with_local_mirror"
        activeCommandTransport -> "native_lsl_commands_with_local_marker_mirror"
        else -> runPackage.lsl.currentAndroidSourceBehavior.ifBlank { "local_lsl_marker_mirror" }
    }
    return JSONObject()
        .put("schema", PHONE_LSL_RUNTIME_STATUS_SCHEMA)
        .put("package_id", runPackage.packageId)
        .put("run_id", runId)
        .put("participant_id", runPackage.participantId)
        .put("session_id", runPackage.sessionId)
        .put("session_group_id", runPackage.sessionGroupId)
        .put("part_session_id", runPackage.partSessionId)
        .put("part_number", runPackage.partNumber)
        .put("asset_strategy", mobilePackageAssetStrategy(runPackage))
        .put("runtime_authority", runPackage.lsl.runtimeAuthority.ifBlank { "android_phone" })
        .put("native_android_lsl_required", runPackage.lsl.nativeAndroidLslRequired)
        .put("native_transport", "liblsl")
        .put("native_transport_available", nativeAvailable)
        .put("native_marker_transport_enabled", activeMarkerTransport)
        .put("native_marker_timestamp_strategy", "android_elapsed_realtime_plus_open_lsl_clock_offset")
        .put("command_receiver_available", activeCommandTransport)
        .put("current_android_source_behavior", sourceBehavior)
        .put("reason", if (activeMarkerTransport && activeCommandTransport) "" else reason.ifBlank { "native_lsl_transport_not_fully_enabled" })
        .put("native_bridge", phoneNativeLslStatusJson(nativeBridgeStatus, markerTransportStatus, commandTransportStatus))
        .put(
            "streams",
            JSONObject()
                .put("rich_markers", richName)
                .put("numeric_triggers", numericName)
                .put("command_signals", commandName)
                .put("command_acks", ackName),
        )
        .put("stream_descriptions", phoneLslStreamDescriptions(runPackage, runId))
        .put(
            "command_protocol",
            JSONObject()
                .put("command_schema", PHONE_LSL_COMMAND_SCHEMA)
                .put("ack_schema", PHONE_LSL_ACK_SCHEMA)
                .put("command_channels", stringArray(PHONE_LSL_COMMAND_CHANNELS))
                .put("ack_channels", stringArray(PHONE_LSL_ACK_CHANNELS))
                .put("supported_commands", stringArray(supportedPhoneCommands(runPackage)))
                .put("token_required", true)
                .put("token_payload_fields", stringArray(listOf("token", "companion_token"))),
        )
        .put(
            "privacy",
            JSONObject()
                .put("default", runPackage.lsl.privacyDefault.ifBlank { "metadata_payload_only" })
                .put("participant_demographics_location", "metadata_and_payload_artifacts")
                .put("demographics_in_stream_name", false),
        )
}

internal fun phoneLslStreamDescriptions(runPackage: MobileRunPackage, runId: String): JSONObject {
    val richName = runPackage.lsl.richMarkersName.ifBlank { PHONE_LSL_RICH_MARKER_STREAM_NAME }
    val numericName = runPackage.lsl.numericTriggersName.ifBlank { PHONE_LSL_NUMERIC_TRIGGER_STREAM_NAME }
    val commandName = runPackage.lsl.commandSignalsName.ifBlank { PHONE_LSL_COMMAND_STREAM_NAME }
    val ackName = runPackage.lsl.commandAcksName.ifBlank { PHONE_LSL_ACK_STREAM_NAME }
    val runToken = phoneLslSourceIdToken(runId)
    return JSONObject()
        .put("schema", "pps-android-lsl-stream-descriptions.v1")
        .put("runtime_authority", runPackage.lsl.runtimeAuthority.ifBlank { "android_phone" })
        .put("privacy", JSONObject()
            .put("default", runPackage.lsl.privacyDefault.ifBlank { "metadata_payload_only" })
            .put("demographics_in_stream_name", false)
            .put("participant_demographics_location", "metadata_and_payload_artifacts"))
        .put(
            "rich_markers",
            JSONObject()
                .put("name", richName)
                .put("type", "Markers")
                .put("role", "outlet")
                .put("channel_format", "string")
                .put("channel_count", PHONE_LSL_MARKER_CHANNELS.size)
                .put("nominal_srate_hz", 0.0)
                .put("source_id", "pps-android-markers-v2-$runToken")
                .put("marker_version", PHONE_LSL_MARKER_VERSION)
                .put("channel_labels", stringArray(PHONE_LSL_MARKER_CHANNELS)),
        )
        .put(
            "numeric_triggers",
            JSONObject()
                .put("name", numericName)
                .put("type", "TriggerCodes")
                .put("role", "outlet")
                .put("channel_format", "int32")
                .put("channel_count", 1)
                .put("nominal_srate_hz", 0.0)
                .put("source_id", "pps-android-trigger-codes-$runToken")
                .put("channel_labels", stringArray(listOf("event_code"))),
        )
        .put(
            "command_signals",
            JSONObject()
                .put("name", commandName)
                .put("type", "CommandSignals")
                .put("role", "inlet")
                .put("channel_format", "string")
                .put("channel_count", PHONE_LSL_COMMAND_CHANNELS.size)
                .put("nominal_srate_hz", 0.0)
                .put("source_id_pattern", "pps-*-command-signals-v1-*")
                .put("channel_labels", stringArray(PHONE_LSL_COMMAND_CHANNELS))
                .put("token_required", true),
        )
        .put(
            "command_acks",
            JSONObject()
                .put("name", ackName)
                .put("type", "CommandAcks")
                .put("role", "outlet")
                .put("channel_format", "string")
                .put("channel_count", PHONE_LSL_ACK_CHANNELS.size)
                .put("nominal_srate_hz", 0.0)
                .put("source_id", "pps-android-command-acks-v1-$runToken")
                .put("channel_labels", stringArray(PHONE_LSL_ACK_CHANNELS)),
        )
}

internal fun phoneCommandAckForSample(
    sample: List<Any?>,
    runPackage: MobileRunPackage,
    expectedToken: String,
    receiverId: String = "android_phone",
    receivedLslTime: Double = 0.0,
    appliedLslTime: Double = receivedLslTime,
    ackLslTime: Double = appliedLslTime,
    handler: (PhoneLslCommandSignal) -> PhoneLslCommandApplicationResult,
): PhoneLslCommandAck {
    val signal = try {
        phoneCommandFromSample(sample)
    } catch (error: IllegalArgumentException) {
        return PhoneLslCommandAck(
            commandId = "",
            sessionId = "",
            receiverId = receiverId,
            status = "rejected",
            reason = error.message ?: "invalid_command_sample",
            receivedLslTime = receivedLslTime,
            appliedLslTime = appliedLslTime,
            ackLslTime = ackLslTime,
            payload = JSONObject().put("error", "invalid_command_sample"),
        )
    }
    return phoneCommandAckForSignal(
        signal = signal,
        runPackage = runPackage,
        expectedToken = expectedToken,
        receiverId = receiverId,
        receivedLslTime = receivedLslTime,
        appliedLslTime = appliedLslTime,
        ackLslTime = ackLslTime,
        handler = handler,
    )
}

internal fun phoneCommandAckForSignal(
    signal: PhoneLslCommandSignal,
    runPackage: MobileRunPackage,
    expectedToken: String,
    receiverId: String = "android_phone",
    receivedLslTime: Double = 0.0,
    appliedLslTime: Double = receivedLslTime,
    ackLslTime: Double = appliedLslTime,
    handler: (PhoneLslCommandSignal) -> PhoneLslCommandApplicationResult,
): PhoneLslCommandAck {
    val rejection = phoneCommandRejection(signal, runPackage, expectedToken)
    if (rejection != null) {
        return PhoneLslCommandAck(
            commandId = signal.commandId,
            sessionId = signal.sessionId,
            receiverId = receiverId,
            status = "rejected",
            reason = rejection,
            receivedLslTime = receivedLslTime,
            appliedLslTime = appliedLslTime,
            ackLslTime = ackLslTime,
            payload = JSONObject()
                .put("command", signal.command)
                .put("package_id", runPackage.packageId),
        )
    }
    val result = try {
        handler(signal)
    } catch (error: Throwable) {
        PhoneLslCommandApplicationResult(
            status = "rejected",
            reason = error.message ?: error::class.java.simpleName,
            payload = JSONObject().put("exception", error::class.java.simpleName),
        )
    }
    return PhoneLslCommandAck(
        commandId = signal.commandId,
        sessionId = signal.sessionId,
        receiverId = receiverId,
        status = result.status.ifBlank { "applied" },
        reason = result.reason,
        receivedLslTime = receivedLslTime,
        appliedLslTime = appliedLslTime,
        ackLslTime = ackLslTime,
        payload = JSONObject(result.payload.toString()),
    )
}

private fun phoneCommandRejection(
    signal: PhoneLslCommandSignal,
    runPackage: MobileRunPackage,
    expectedToken: String,
): String? {
    val validSessions = listOf(
        runPackage.sessionId,
        runPackage.sessionGroupId,
        runPackage.partSessionId,
        runPackage.packageId,
    ).filter { it.isNotBlank() }.toSet()
    if (validSessions.isNotEmpty() && signal.sessionId !in validSessions) {
        return "session_mismatch"
    }
    if (expectedToken.isBlank()) {
        return "receiver_token_not_configured"
    }
    val token = signal.payload.optString("token").ifBlank { signal.payload.optString("companion_token") }
    if (token != expectedToken) {
        return "invalid_token"
    }
    if (signal.command !in supportedPhoneCommands(runPackage)) {
        return "unsupported_command"
    }
    return null
}

private fun supportedPhoneCommands(runPackage: MobileRunPackage): List<String> =
    runPackage.lsl.supportedCommands.ifEmpty { DEFAULT_PHONE_LSL_SUPPORTED_COMMANDS }

private fun jsonObjectFromString(raw: String): JSONObject =
    try {
        JSONObject(raw.ifBlank { "{}" })
    } catch (error: Exception) {
        throw IllegalArgumentException("Command payload JSON must be an object.", error)
    }

private fun phoneLslSourceIdToken(value: String): String =
    value.replace(Regex("[^A-Za-z0-9._-]+"), "-").trim('-', '.', '_').ifBlank { "phone-run" }

private fun stringArray(values: List<String>): JSONArray =
    JSONArray().also { array -> values.forEach { array.put(it) } }
