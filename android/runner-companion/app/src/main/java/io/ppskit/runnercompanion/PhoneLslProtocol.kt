package io.ppskit.runnercompanion

import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest

internal const val PHONE_LSL_RUNTIME_STATUS_SCHEMA = "pps-android-lsl-runtime-status.v1"
internal const val PHONE_LSL_MARKER_VERSION = "2.0"
internal const val PHONE_LSL_RICH_MARKER_STREAM_NAME = "PPSMarkersV2"
internal const val PHONE_LSL_NUMERIC_TRIGGER_STREAM_NAME = "PPSTriggerCodes"
internal const val PHONE_LSL_COMMAND_SCHEMA = "pps-lsl-command.v1"
internal const val PHONE_LSL_ACK_SCHEMA = "pps-lsl-command-ack.v1"
internal const val PHONE_LSL_COMMAND_STREAM_NAME = "PPSCommandSignalsV1"
internal const val PHONE_LSL_ACK_STREAM_NAME = "PPSCommandAcksV1"
internal const val PHONE_LSL_COMMAND_REJECTION_PAYLOAD_SCHEMA = "pps-android-phone-command-rejection.v1"
internal const val PHONE_LSL_COMMAND_SAMPLE_REJECTION_PAYLOAD_SCHEMA = "pps-android-phone-command-sample-rejection.v1"
internal const val PHONE_LSL_COMMAND_HANDLER_REJECTION_PAYLOAD_SCHEMA = "pps-android-phone-command-handler-rejection.v1"

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
    val rawSample: List<String> = emptyList(),
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
        rawSample = values,
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
    participantMetadata: JSONObject? = null,
    hapticCapability: JSONObject? = null,
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
    val status = JSONObject()
        .put("schema", PHONE_LSL_RUNTIME_STATUS_SCHEMA)
        .put("role", "runner")
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
    phoneParticipantMetadataSummary(participantMetadata)?.let { status.put("participant_metadata_summary", it) }
    phoneHapticCapabilitySummary(hapticCapability)?.let { status.put("haptic_capability_summary", it) }
    status.put("stream_descriptions", phoneLslStreamDescriptions(runPackage, runId, participantMetadata, hapticCapability))
    return status
}

internal fun phoneLslStreamDescriptions(
    runPackage: MobileRunPackage,
    runId: String,
    participantMetadata: JSONObject? = null,
    hapticCapability: JSONObject? = null,
): JSONObject {
    val richName = runPackage.lsl.richMarkersName.ifBlank { PHONE_LSL_RICH_MARKER_STREAM_NAME }
    val numericName = runPackage.lsl.numericTriggersName.ifBlank { PHONE_LSL_NUMERIC_TRIGGER_STREAM_NAME }
    val commandName = runPackage.lsl.commandSignalsName.ifBlank { PHONE_LSL_COMMAND_STREAM_NAME }
    val ackName = runPackage.lsl.commandAcksName.ifBlank { PHONE_LSL_ACK_STREAM_NAME }
    val runToken = phoneLslSourceIdToken(runId)
    val sessionMetadataJson = phoneLslSessionMetadataJson(runPackage, participantMetadata, hapticCapability)
    return JSONObject()
        .put("schema", "pps-android-lsl-stream-descriptions.v1")
        .put("runtime_authority", runPackage.lsl.runtimeAuthority.ifBlank { "android_phone" })
        .put("role", "runner")
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
                .put("session_id", runPackage.sessionId)
                .put("participant_id", runPackage.participantId)
                .put("session_group_id", runPackage.sessionGroupId)
                .put("part_session_id", runPackage.partSessionId)
                .put("part_number", runPackage.partNumber)
                .put("run_id", runId)
                .put("session_metadata_json", sessionMetadataJson)
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
                .put("session_id", runPackage.sessionId)
                .put("participant_id", runPackage.participantId)
                .put("session_group_id", runPackage.sessionGroupId)
                .put("part_session_id", runPackage.partSessionId)
                .put("part_number", runPackage.partNumber)
                .put("run_id", runId)
                .put("session_metadata_json", sessionMetadataJson)
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

internal fun phoneLslSessionMetadataJson(
    runPackage: MobileRunPackage,
    participantMetadata: JSONObject? = null,
    hapticCapability: JSONObject? = null,
): String {
    val payload = JSONObject()
        .put("package_id", runPackage.packageId)
        .put("asset_strategy", mobilePackageAssetStrategy(runPackage))
        .put("package_asset_strategy", runPackage.reconstruction.packageAssetStrategy)
        .put("schedule_hash", runPackage.reconstruction.scheduleHash)
        .put("participant_roster_count", runPackage.participantRoster.size)
        .put("randomization_seed", runPackage.randomizationSeed)
        .put("source_segment_hashes", runPackage.sourceSegmentHashes.toJsonObject())
        .put("study_hierarchy", stringArray(runPackage.reconstruction.studyHierarchy))
        .put("source_run_setup_manifest_path", runPackage.reconstruction.sourceRunSetupManifestPath)
        .put("source_run_setup_sha256", runPackage.reconstruction.sourceRunSetupSha256)
        .put("privacy_default", runPackage.lsl.privacyDefault.ifBlank { "metadata_payload_only" })
        .put("demographics_in_stream_name", false)
    phoneParticipantMetadataSummary(participantMetadata)?.let { payload.put("participant_metadata_summary", it) }
    phoneHapticCapabilitySummary(hapticCapability)?.let { payload.put("haptic_capability_summary", it) }
    return payload.toString()
}

internal fun phoneParticipantMetadataSummary(participantMetadata: JSONObject?): JSONObject? {
    if (participantMetadata == null || participantMetadata.length() == 0) return null
    return JSONObject()
        .put("schema", "pps-android-lsl-participant-metadata-summary.v1")
        .put("participant_id", participantMetadata.optString("participant_id", ""))
        .put("session_id", participantMetadata.optString("session_id", ""))
        .put("session_group_id", participantMetadata.optString("session_group_id", ""))
        .put("part_session_id", participantMetadata.optString("part_session_id", ""))
        .put("part_number", participantMetadata.optString("part_number", ""))
        .put("age_years", participantMetadata.optString("age_years", ""))
        .put("handedness", participantMetadata.optString("handedness", ""))
        .put("gender", participantMetadata.optString("gender", ""))
        .put("tactile_threshold_percent", participantMetadata.opt("tactile_threshold_percent") ?: JSONObject.NULL)
        .put("tactile_threshold_source", participantMetadata.optString("tactile_threshold_source", ""))
        .put("tactile_threshold_calibration_status", participantMetadata.optString("tactile_threshold_calibration_status", ""))
        .put("stream_privacy", participantMetadata.optString("stream_privacy", "metadata_payload_only"))
}

internal fun phoneHapticCapabilitySummary(hapticCapability: JSONObject?): JSONObject? {
    if (hapticCapability == null || hapticCapability.length() == 0) return null
    return JSONObject()
        .put("schema", "pps-android-lsl-haptic-capability-summary.v1")
        .put("has_vibrator", hapticCapability.optBoolean("has_vibrator", false))
        .put("has_amplitude_control", hapticCapability.optBoolean("has_amplitude_control", false))
        .put("calibration_policy", hapticCapability.optString("calibration_policy", ""))
        .put("calibration_status", hapticCapability.optString("calibration_status", ""))
        .put("recommended_threshold_percent", hapticCapability.opt("recommended_threshold_percent") ?: JSONObject.NULL)
        .put("recommended_amplitude", hapticCapability.opt("recommended_amplitude") ?: JSONObject.NULL)
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
        val rawValues = sample.map { it?.toString() ?: "" }
        val fallbackCommandId = rawValues.getOrNull(1).orEmpty().ifBlank {
            "invalid-lsl-command-${redactedSampleHash(rawValues).take(12)}"
        }
        val fallbackSessionId = rawValues.getOrNull(2).orEmpty().ifBlank {
            runPackage.partSessionId
                .ifBlank { runPackage.sessionId }
                .ifBlank { runPackage.sessionGroupId }
                .ifBlank { runPackage.packageId }
        }
        val reason = "invalid_command_sample"
        return PhoneLslCommandAck(
            commandId = fallbackCommandId,
            sessionId = fallbackSessionId,
            receiverId = receiverId,
            status = "rejected",
            reason = reason,
            receivedLslTime = receivedLslTime,
            appliedLslTime = appliedLslTime,
            ackLslTime = ackLslTime,
            payload = phoneMalformedCommandSampleAckPayload(
                rawValues = rawValues,
                runPackage = runPackage,
                commandId = fallbackCommandId,
                sessionId = fallbackSessionId,
                reason = reason,
                parseError = error.message ?: error::class.java.simpleName,
            ),
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
            payload = phoneRejectedCommandAckPayload(signal, runPackage, rejection),
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
    val status = result.status.ifBlank { "applied" }
    val payload = if (status == "rejected") {
        phoneHandlerRejectedCommandAckPayload(signal, runPackage, result.reason, result.payload)
    } else {
        phoneCommandAckPayload(signal, result.payload)
    }
    return PhoneLslCommandAck(
        commandId = signal.commandId,
        sessionId = signal.sessionId,
        receiverId = receiverId,
        status = status,
        reason = result.reason,
        receivedLslTime = receivedLslTime,
        appliedLslTime = appliedLslTime,
        ackLslTime = ackLslTime,
        payload = payload,
    )
}

private val PHONE_COMMAND_ACK_ECHO_PAYLOAD_FIELDS = listOf(
    "package_id",
    "participant_id",
    "target_session_id",
    "target_part_session_id",
    "target_session_group_id",
    "target_part_number",
    "requested_by",
    "current_android_source_behavior",
    "current_pc_source_behavior",
)

private fun phoneCommandAckPayload(signal: PhoneLslCommandSignal, basePayload: JSONObject): JSONObject {
    val payload = JSONObject(basePayload.toString())
    if (!payload.has("receiver_role")) {
        payload.put("receiver_role", "runner")
    }
    if (!payload.has("command")) {
        payload.put("command", signal.command)
    }
    if (!payload.has("target_session_id") && signal.sessionId.isNotBlank()) {
        payload.put("target_session_id", signal.sessionId)
    }
    PHONE_COMMAND_ACK_ECHO_PAYLOAD_FIELDS.forEach { field ->
        if (!payload.has(field) && signal.payload.has(field) && !signal.payload.isNull(field)) {
            payload.put(field, signal.payload.opt(field))
        }
    }
    return payload
}

private fun phoneRejectedCommandAckPayload(
    signal: PhoneLslCommandSignal,
    runPackage: MobileRunPackage,
    reason: String,
): JSONObject =
    phoneCommandAckPayload(
        signal,
        JSONObject()
            .put("schema", PHONE_LSL_COMMAND_REJECTION_PAYLOAD_SCHEMA)
            .put("status", "rejected")
            .put("reason", reason)
            .put("rejected_before_handler", true)
            .put("command", signal.command)
            .put("package_id", runPackage.packageId)
            .put("participant_id", runPackage.participantId)
            .put("session_id", runPackage.sessionId)
            .put("part_session_id", runPackage.partSessionId)
            .put("session_group_id", runPackage.sessionGroupId)
            .put("part_number", runPackage.partNumber)
            .put("requested_session_id", signal.sessionId)
            .put("requested_package_id", signal.payload.optString("package_id"))
            .put("requested_participant_id", signal.payload.optString("participant_id"))
            .put("requested_target_session_id", signal.payload.optString("target_session_id"))
            .put("requested_target_part_session_id", signal.payload.optString("target_part_session_id"))
            .put("requested_target_session_group_id", signal.payload.optString("target_session_group_id"))
            .put("requested_target_part_number", signal.payload.optString("target_part_number"))
            .put("supported_commands", stringArray(supportedPhoneCommands(runPackage))),
    )

private fun phoneMalformedCommandSampleAckPayload(
    rawValues: List<String>,
    runPackage: MobileRunPackage,
    commandId: String,
    sessionId: String,
    reason: String,
    parseError: String,
): JSONObject =
    JSONObject()
        .put("schema", PHONE_LSL_COMMAND_SAMPLE_REJECTION_PAYLOAD_SCHEMA)
        .put("receiver_role", "runner")
        .put("status", "rejected")
        .put("reason", reason)
        .put("parse_error", parseError)
        .put("rejected_before_handler", true)
        .put("command", "invalid_lsl_command")
        .put("malformed_sample_id", commandId)
        .put("package_id", runPackage.packageId)
        .put("participant_id", runPackage.participantId)
        .put("session_id", sessionId)
        .put("part_session_id", runPackage.partSessionId)
        .put("session_group_id", runPackage.sessionGroupId)
        .put("part_number", runPackage.partNumber)
        .put("raw_sample_channel_count", rawValues.size)
        .put("expected_channel_count", PHONE_LSL_COMMAND_CHANNELS.size)
        .put("raw_sample_schema", rawValues.getOrNull(0).orEmpty())
        .put("raw_command_id", rawValues.getOrNull(1).orEmpty())
        .put("raw_session_id", rawValues.getOrNull(2).orEmpty())
        .put("raw_sender_id", rawValues.getOrNull(3).orEmpty())
        .put("raw_command", rawValues.getOrNull(4).orEmpty())
        .put("raw_issued_lsl_time", rawValues.getOrNull(5).orEmpty())
        .put("raw_payload_redacted", rawValues.drop(6).any { it.isNotBlank() })
        .put("raw_sample_preview", stringArray(redactedCommandSamplePreview(rawValues)))
        .put("supported_commands", stringArray(supportedPhoneCommands(runPackage)))

private fun phoneHandlerRejectedCommandAckPayload(
    signal: PhoneLslCommandSignal,
    runPackage: MobileRunPackage,
    reason: String,
    handlerPayload: JSONObject,
): JSONObject =
    phoneCommandAckPayload(
        signal,
        JSONObject()
            .put("schema", PHONE_LSL_COMMAND_HANDLER_REJECTION_PAYLOAD_SCHEMA)
            .put("status", "rejected")
            .put("reason", reason)
            .put("rejected_before_handler", false)
            .put("handler_completed", !handlerPayload.has("exception"))
            .put("command", signal.command)
            .put("package_id", runPackage.packageId)
            .put("participant_id", runPackage.participantId)
            .put("session_id", runPackage.sessionId)
            .put("part_session_id", runPackage.partSessionId)
            .put("session_group_id", runPackage.sessionGroupId)
            .put("part_number", runPackage.partNumber)
            .put("requested_session_id", signal.sessionId)
            .put("requested_package_id", signal.payload.optString("package_id"))
            .put("requested_participant_id", signal.payload.optString("participant_id"))
            .put("requested_target_session_id", signal.payload.optString("target_session_id"))
            .put("requested_target_part_session_id", signal.payload.optString("target_part_session_id"))
            .put("requested_target_session_group_id", signal.payload.optString("target_session_group_id"))
            .put("requested_target_part_number", signal.payload.optString("target_part_number"))
            .put("handler_payload_schema", handlerPayload.optString("schema"))
            .put("handler_payload", JSONObject(handlerPayload.toString()))
            .put("supported_commands", stringArray(supportedPhoneCommands(runPackage))),
    )

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
    val payloadPackageId = signal.payload.optString("package_id")
    if (payloadPackageId.isNotBlank() && runPackage.packageId.isNotBlank() && payloadPackageId != runPackage.packageId) {
        return "package_mismatch"
    }
    val targetSessionId = signal.payload.optString("target_session_id")
    if (targetSessionId.isNotBlank() && validSessions.isNotEmpty() && targetSessionId !in validSessions) {
        return "target_session_mismatch"
    }
    val targetPartSessionId = signal.payload.optString("target_part_session_id")
    if (targetPartSessionId.isNotBlank() && runPackage.partSessionId.isNotBlank() && targetPartSessionId != runPackage.partSessionId) {
        return "part_session_mismatch"
    }
    val targetSessionGroupId = signal.payload.optString("target_session_group_id")
    if (targetSessionGroupId.isNotBlank() && runPackage.sessionGroupId.isNotBlank() && targetSessionGroupId != runPackage.sessionGroupId) {
        return "session_group_mismatch"
    }
    val targetPartNumber = signal.payload.optString("target_part_number")
    if (targetPartNumber.isNotBlank() && runPackage.partNumber.isNotBlank() && targetPartNumber != runPackage.partNumber) {
        return "part_number_mismatch"
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

private fun redactedCommandSamplePreview(values: List<String>): List<String> =
    values.mapIndexed { index, value ->
        if (index >= 6 && value.isNotBlank()) "<redacted>" else value
    }

private fun redactedSampleHash(values: List<String>): String {
    val digest = MessageDigest.getInstance("SHA-256")
    digest.update(redactedCommandSamplePreview(values).joinToString("\u001F").toByteArray(Charsets.UTF_8))
    return digest.digest().joinToString("") { "%02x".format(it) }
}

private fun stringArray(values: List<String>): JSONArray =
    JSONArray().also { array -> values.forEach { array.put(it) } }
