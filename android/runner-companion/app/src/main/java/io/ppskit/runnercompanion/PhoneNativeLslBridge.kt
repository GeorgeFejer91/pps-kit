package io.ppskit.runnercompanion

import org.json.JSONArray
import org.json.JSONObject

internal const val PHONE_NATIVE_LSL_BRIDGE_STATUS_SCHEMA = "pps-android-native-lsl-bridge-status.v1"

internal interface PhoneNativeLslBridge {
    fun status(): PhoneNativeLslBridgeStatus
    fun openMarkerTransport(runPackage: MobileRunPackage, runId: String): PhoneLslMarkerTransport
}

internal interface PhoneLslMarkerTransport : AutoCloseable {
    val status: PhoneNativeLslBridgeStatus
    fun localClock(): Double
    fun pushMarker(marker: JSONObject, timestamp: Double = localClock()): Boolean
}

internal data class PhoneNativeLslBridgeStatus(
    val available: Boolean,
    val enabled: Boolean,
    val backend: String,
    val reason: String = "",
    val libraryVersion: String = "",
    val libraryInfo: String = "",
) {
    fun toJson(): JSONObject =
        JSONObject()
            .put("schema", PHONE_NATIVE_LSL_BRIDGE_STATUS_SCHEMA)
            .put("available", available)
            .put("enabled", enabled)
            .put("backend", backend)
            .put("reason", reason)
            .put("library_version", libraryVersion)
            .put("library_info", libraryInfo)
}

internal object PhoneNativeLslBridgeFactory {
    fun create(classLoader: ClassLoader = Thread.currentThread().contextClassLoader ?: PhoneNativeLslBridgeFactory::class.java.classLoader): PhoneNativeLslBridge =
        ReflectiveLiblslBridge.create(classLoader)
}

private class MissingPhoneNativeLslBridge(private val status: PhoneNativeLslBridgeStatus) : PhoneNativeLslBridge {
    override fun status(): PhoneNativeLslBridgeStatus = status

    override fun openMarkerTransport(runPackage: MobileRunPackage, runId: String): PhoneLslMarkerTransport =
        NoopPhoneLslMarkerTransport(status)
}

private class NoopPhoneLslMarkerTransport(override val status: PhoneNativeLslBridgeStatus) : PhoneLslMarkerTransport {
    override fun localClock(): Double = System.nanoTime() / 1_000_000_000.0
    override fun pushMarker(marker: JSONObject, timestamp: Double): Boolean = false
    override fun close() = Unit
}

private class ReflectiveLiblslBridge private constructor(
    private val lslClass: Class<*>,
    private val streamInfoClass: Class<*>,
    private val streamOutletClass: Class<*>,
    private val channelFormatClass: Class<*>,
    private val xmlElementClass: Class<*>,
    private val status: PhoneNativeLslBridgeStatus,
) : PhoneNativeLslBridge {
    override fun status(): PhoneNativeLslBridgeStatus = status

    override fun openMarkerTransport(runPackage: MobileRunPackage, runId: String): PhoneLslMarkerTransport {
        if (!status.available) return NoopPhoneLslMarkerTransport(status)
        return runCatching {
            val richInfo = streamInfo(
                name = runPackage.lsl.richMarkersName.ifBlank { PHONE_LSL_RICH_MARKER_STREAM_NAME },
                type = "Markers",
                channelCount = PHONE_LSL_MARKER_CHANNELS.size,
                channelFormat = channelFormat("string"),
                sourceId = "pps-android-markers-v2-${sourceIdToken(runId)}",
            )
            appendCommonDescription(
                info = richInfo,
                runPackage = runPackage,
                runId = runId,
                channelLabels = PHONE_LSL_MARKER_CHANNELS,
                channelType = "Marker",
            )
            val numericInfo = streamInfo(
                name = runPackage.lsl.numericTriggersName.ifBlank { PHONE_LSL_NUMERIC_TRIGGER_STREAM_NAME },
                type = "TriggerCodes",
                channelCount = 1,
                channelFormat = channelFormat("int32"),
                sourceId = "pps-android-trigger-codes-${sourceIdToken(runId)}",
            )
            appendCommonDescription(
                info = numericInfo,
                runPackage = runPackage,
                runId = runId,
                channelLabels = listOf("event_code"),
                channelType = "Trigger",
            )
            ReflectivePhoneLslMarkerTransport(
                bridge = this,
                richOutlet = outlet(richInfo),
                numericOutlet = outlet(numericInfo),
                status = status.copy(enabled = true, reason = ""),
            )
        }.getOrElse { error ->
            NoopPhoneLslMarkerTransport(
                status.copy(enabled = false, reason = "could_not_create_lsl_outlets:${error.message ?: error::class.java.simpleName}"),
            )
        }
    }

    fun localClock(): Double =
        runCatching { (lslClass.getMethod("local_clock").invoke(null) as Number).toDouble() }
            .getOrDefault(System.nanoTime() / 1_000_000_000.0)

    fun pushStringSample(outlet: Any, sample: List<String>, timestamp: Double): Boolean =
        runCatching {
            streamOutletClass
                .getMethod("push_sample", Array<String>::class.java, java.lang.Double.TYPE, java.lang.Boolean.TYPE)
                .invoke(outlet, sample.toTypedArray(), timestamp, true)
            true
        }.getOrDefault(false)

    fun pushIntSample(outlet: Any, sample: IntArray, timestamp: Double): Boolean =
        runCatching {
            streamOutletClass
                .getMethod("push_sample", IntArray::class.java, java.lang.Double.TYPE, java.lang.Boolean.TYPE)
                .invoke(outlet, sample, timestamp, true)
            true
        }.getOrDefault(false)

    fun closeOutlet(outlet: Any) {
        runCatching { streamOutletClass.getMethod("close").invoke(outlet) }
    }

    private fun streamInfo(name: String, type: String, channelCount: Int, channelFormat: Int, sourceId: String): Any =
        streamInfoClass
            .getConstructor(
                String::class.java,
                String::class.java,
                java.lang.Integer.TYPE,
                java.lang.Double.TYPE,
                java.lang.Integer.TYPE,
                String::class.java,
            )
            .newInstance(name, type, channelCount, 0.0, channelFormat, sourceId)

    private fun outlet(info: Any): Any =
        streamOutletClass.getConstructor(streamInfoClass).newInstance(info)

    private fun channelFormat(name: String): Int =
        channelFormatClass.getField(name).getInt(null)

    private fun appendCommonDescription(
        info: Any,
        runPackage: MobileRunPackage,
        runId: String,
        channelLabels: List<String>,
        channelType: String,
    ) {
        runCatching {
            val desc = streamInfoClass.getMethod("desc").invoke(info) ?: return@runCatching
            appendChildValue(desc, "marker_version", PHONE_LSL_MARKER_VERSION)
            appendChildValue(desc, "session_id", runPackage.sessionId)
            appendChildValue(desc, "participant_id", runPackage.participantId)
            appendChildValue(desc, "session_group_id", runPackage.sessionGroupId)
            appendChildValue(desc, "part_session_id", runPackage.partSessionId)
            appendChildValue(desc, "part_number", runPackage.partNumber)
            appendChildValue(desc, "run_id", runId)
            appendChildValue(
                desc,
                "session_metadata_json",
                JSONObject()
                    .put("package_id", runPackage.packageId)
                    .put("privacy_default", runPackage.lsl.privacyDefault.ifBlank { "metadata_payload_only" })
                    .put("demographics_in_stream_name", false)
                    .toString(),
            )
            val channels = xmlElementClass.getMethod("append_child", String::class.java).invoke(desc, "channels") ?: return@runCatching
            channelLabels.forEach { label ->
                val channel = xmlElementClass.getMethod("append_child", String::class.java).invoke(channels, "channel") ?: return@forEach
                appendChildValue(channel, "label", label)
                appendChildValue(channel, "type", channelType)
            }
        }
    }

    private fun appendChildValue(element: Any, name: String, value: String) {
        xmlElementClass.getMethod("append_child_value", String::class.java, String::class.java).invoke(element, name, value)
    }

    companion object {
        fun create(classLoader: ClassLoader): PhoneNativeLslBridge {
            return try {
                val lslClass = Class.forName("edu.ucsd.sccn.LSL", true, classLoader)
                val streamInfoClass = Class.forName("edu.ucsd.sccn.LSL\$StreamInfo", true, classLoader)
                val streamOutletClass = Class.forName("edu.ucsd.sccn.LSL\$StreamOutlet", true, classLoader)
                val channelFormatClass = Class.forName("edu.ucsd.sccn.LSL\$ChannelFormat", true, classLoader)
                val xmlElementClass = Class.forName("edu.ucsd.sccn.LSL\$XMLElement", true, classLoader)
                val version = runCatching { lslClass.getMethod("library_version").invoke(null)?.toString().orEmpty() }.getOrDefault("")
                val info = runCatching { lslClass.getMethod("library_info").invoke(null)?.toString().orEmpty() }.getOrDefault("")
                ReflectiveLiblslBridge(
                    lslClass = lslClass,
                    streamInfoClass = streamInfoClass,
                    streamOutletClass = streamOutletClass,
                    channelFormatClass = channelFormatClass,
                    xmlElementClass = xmlElementClass,
                    status = PhoneNativeLslBridgeStatus(
                        available = true,
                        enabled = false,
                        backend = "liblsl-android-reflection",
                        libraryVersion = version,
                        libraryInfo = info,
                    ),
                )
            } catch (error: Throwable) {
                MissingPhoneNativeLslBridge(
                    PhoneNativeLslBridgeStatus(
                        available = false,
                        enabled = false,
                        backend = "liblsl-android-reflection",
                        reason = "liblsl_android_class_unavailable:${error.message ?: error::class.java.simpleName}",
                    ),
                )
            }
        }
    }
}

private class ReflectivePhoneLslMarkerTransport(
    private val bridge: ReflectiveLiblslBridge,
    private val richOutlet: Any,
    private val numericOutlet: Any,
    override val status: PhoneNativeLslBridgeStatus,
) : PhoneLslMarkerTransport {
    override fun localClock(): Double = bridge.localClock()

    override fun pushMarker(marker: JSONObject, timestamp: Double): Boolean {
        val richOk = bridge.pushStringSample(richOutlet, phoneMarkerToRichSample(marker), timestamp)
        val numericOk = bridge.pushIntSample(numericOutlet, intArrayOf(phoneMarkerTriggerCode(marker)), timestamp)
        return richOk && numericOk
    }

    override fun close() {
        bridge.closeOutlet(richOutlet)
        bridge.closeOutlet(numericOutlet)
    }
}

internal fun phoneNativeLslStatusJson(
    bridgeStatus: PhoneNativeLslBridgeStatus,
    markerTransportStatus: PhoneNativeLslBridgeStatus? = null,
): JSONObject =
    JSONObject()
        .put("bridge", bridgeStatus.toJson())
        .put("marker_transport", markerTransportStatus?.toJson() ?: JSONObject.NULL)
        .put("required_local_aar", "android/runner-companion/app/libs/liblsl-Android.aar")
        .put("stream_names", JSONObject()
            .put("rich_markers", PHONE_LSL_RICH_MARKER_STREAM_NAME)
            .put("numeric_triggers", PHONE_LSL_NUMERIC_TRIGGER_STREAM_NAME)
            .put("command_signals", PHONE_LSL_COMMAND_STREAM_NAME)
            .put("command_acks", PHONE_LSL_ACK_STREAM_NAME))
        .put("marker_channels", stringArray(PHONE_LSL_MARKER_CHANNELS))

private fun sourceIdToken(value: String): String =
    value.replace(Regex("[^A-Za-z0-9._-]+"), "-").trim('-', '.', '_').ifBlank { "phone-run" }

private fun stringArray(values: List<String>): JSONArray =
    JSONArray().also { array -> values.forEach { array.put(it) } }
