package io.ppskit.runnercompanion

import android.content.Context
import android.net.wifi.WifiManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.MulticastSocket
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

internal const val COMPANION_DISCOVERY_SCHEMA = "pps-runner-companion-discovery.v1"
internal const val COMPANION_DISCOVERY_SERVICE = "pps-runner-companion"
internal const val COMPANION_DISCOVERY_MULTICAST_GROUP = "239.255.77.83"
internal const val COMPANION_DISCOVERY_PORT = 48767
internal const val COMPANION_DISCOVERY_NETWORK_SCOPE = "same_lan_or_local_hotspot"
internal const val COMPANION_DISCOVERY_TOKEN_DELIVERY = "qr_or_manual_uri_only"
internal const val COMPANION_DISCOVERY_LIMITED_BROADCAST_TARGET = "255.255.255.255"
internal const val COMPANION_DISCOVERY_DIRECTED_BROADCAST_TARGET = "interface_ipv4_directed_broadcasts"
private val companionDiscoveryModes = setOf("pc_runner", "phone_export")
private val companionDiscoveryTransports = setOf("lan", "phone_hotspot", "wifi_direct")
private val companionDiscoveryTokenFields = setOf("token", "companion_token", "pairing_token", "bearer_token", "x_pps_companion_token")
private val companionDiscoveryParticipantFields = setOf(
    "age",
    "gender",
    "handedness",
    "sex",
    "threshold",
    "tactile_threshold",
    "haptic_threshold",
    "participant_metadata",
    "participant_demographics",
    "demographics",
    "participant_id",
    "participant_code",
    "participant_name",
    "subject_id",
    "subject_code",
)
private val companionDiscoveryStreamFields = setOf("stream_name", "stream_names", "lsl_stream_name", "lsl_stream_names", "source_id", "source_ids")

internal data class CompanionDiscoveryAdvertisement(
    val host: String,
    val port: Int,
    val sessionId: String,
    val mode: String,
    val transferId: String,
    val transport: String,
    val serviceName: String,
    val networkScope: String,
    val tokenRequired: Boolean,
) {
    val endpointLabel: String
        get() = "$host:$port"

    fun toPairingUri(token: String): String {
        val cleanToken = token.trim()
        require(cleanToken.isNotEmpty()) { "Discovery packets do not contain the pairing token; scan the QR or paste the full URI." }
        val query = linkedMapOf(
            "v" to if (mode == "phone_export" || transferId.isNotBlank() || transport != "lan") "2" else "1",
            "host" to host,
            "port" to port.toString(),
            "session_id" to sessionId,
            "token" to cleanToken,
        )
        if (mode != "pc_runner" || transferId.isNotBlank() || transport != "lan") {
            query["mode"] = mode
            query["transport"] = transport
            if (transferId.isNotBlank()) query["transfer_id"] = transferId
        }
        return "pps-companion://pair?" + query.entries.joinToString("&") { (key, value) ->
            "${urlEncode(key)}=${urlEncode(value)}"
        }
    }

    fun toPairingInfo(token: String): PairingInfo =
        PairingInfo.parse(toPairingUri(token))

    companion object {
        fun parse(raw: String): CompanionDiscoveryAdvertisement {
            val root = JSONObject(raw.trim())
            assertNoDiscoveryPrivacyLeakage(root)
            require(root.optString("schema") == COMPANION_DISCOVERY_SCHEMA) { "Unsupported discovery schema." }
            require(root.optString("service") == COMPANION_DISCOVERY_SERVICE) { "Unsupported discovery service." }
            require(root.optString("network_scope") == COMPANION_DISCOVERY_NETWORK_SCOPE) { "Unsupported discovery network scope." }
            require(!root.has("token") && !root.has("companion_token")) { "Discovery payload must not contain a pairing token." }
            val discovery = root.optJSONObject("discovery") ?: throw IllegalArgumentException("Discovery transport metadata is missing.")
            require(discovery.optString("udp_multicast_group") == COMPANION_DISCOVERY_MULTICAST_GROUP) { "Discovery multicast group mismatch." }
            require(discovery.optInt("udp_port", 0) == COMPANION_DISCOVERY_PORT) { "Discovery UDP port mismatch." }
            require(discovery.optBoolean("also_sent_as_limited_broadcast", false)) { "Discovery broadcast fallback is missing." }
            val broadcastTargets = discovery.optJSONArray("broadcast_targets")?.toStringSet().orEmpty()
            require(COMPANION_DISCOVERY_LIMITED_BROADCAST_TARGET in broadcastTargets) { "Discovery limited broadcast target is missing." }
            require(COMPANION_DISCOVERY_DIRECTED_BROADCAST_TARGET in broadcastTargets) { "Discovery directed broadcast fallback is missing." }
            require(discovery.optInt("ttl", 0) == 1) { "Discovery TTL must be local-network only." }
            val privacy = root.optJSONObject("privacy") ?: throw IllegalArgumentException("Discovery privacy metadata is missing.")
            require(!privacy.optBoolean("contains_pairing_token", true)) { "Discovery privacy reports pairing-token leakage." }
            require(!privacy.optBoolean("contains_participant_demographics", true)) { "Discovery privacy reports participant-demographic leakage." }
            require(privacy.optBoolean("stream_names_are_generic", false)) { "Discovery privacy must keep stream names generic." }
            val pairing = root.optJSONObject("pairing") ?: throw IllegalArgumentException("Discovery pairing metadata is missing.")
            require(!pairing.has("token") && !pairing.has("companion_token")) { "Discovery pairing metadata must not contain a pairing token." }
            require(pairing.optString("scheme", "pps-companion") == "pps-companion") { "Discovery pairing scheme mismatch." }
            val host = pairing.optString("host").trim()
            val port = pairing.optInt("port", 0)
            val sessionId = pairing.optString("session_id").trim()
            val mode = pairing.optString("mode", "pc_runner").ifBlank { "pc_runner" }
            val transport = pairing.optString("transport", "lan").ifBlank { "lan" }
            val transferId = pairing.optString("transfer_id", "")
            require(host.isNotEmpty()) { "Discovery host is missing." }
            require(port in 1..65535) { "Discovery port is invalid." }
            require(sessionId.isNotEmpty()) { "Discovery session id is missing." }
            require(mode in companionDiscoveryModes) { "Discovery mode is unsupported." }
            require(transport in companionDiscoveryTransports) { "Discovery transport is unsupported." }
            require(pairing.optBoolean("token_required", false)) { "Discovery pairing must require a token." }
            require(pairing.optString("token_delivery") == COMPANION_DISCOVERY_TOKEN_DELIVERY) { "Discovery token delivery mismatch." }
            require(mode != "phone_export" || transferId.isNotBlank()) { "Phone-export discovery requires transfer_id." }
            return CompanionDiscoveryAdvertisement(
                host = host,
                port = port,
                sessionId = sessionId,
                mode = mode,
                transferId = transferId,
                transport = transport,
                serviceName = root.optString("service_name", "PPS Runner Companion").ifBlank { "PPS Runner Companion" },
                networkScope = root.optString("network_scope", COMPANION_DISCOVERY_NETWORK_SCOPE),
                tokenRequired = pairing.optBoolean("token_required", true),
            )
        }

        fun parseOrNull(raw: String?): CompanionDiscoveryAdvertisement? =
            raw?.let { runCatching { parse(it) }.getOrNull() }
    }
}

private fun assertNoDiscoveryPrivacyLeakage(value: Any?) {
    when (value) {
        is JSONObject -> {
            val keys = value.keys()
            while (keys.hasNext()) {
                val key = keys.next()
                val normalized = key.trim().lowercase().replace("-", "_")
                require(normalized !in companionDiscoveryTokenFields) { "Discovery payload must not contain a pairing token." }
                require(normalized !in companionDiscoveryParticipantFields) { "Discovery payload must not contain participant demographics or identifiers." }
                require(normalized !in companionDiscoveryStreamFields) { "Discovery payload must not contain LSL stream names." }
                assertNoDiscoveryPrivacyLeakage(value.opt(key))
            }
        }
        is JSONArray -> {
            for (index in 0 until value.length()) {
                assertNoDiscoveryPrivacyLeakage(value.opt(index))
            }
        }
    }
}

private fun JSONArray.toStringSet(): Set<String> =
    (0 until length()).mapNotNull { index ->
        val value = optString(index).trim()
        if (value.isBlank()) null else value
    }.toSet()

internal suspend fun listenForCompanionDiscoveryOnce(
    context: Context,
    timeoutMs: Int = 4000,
): CompanionDiscoveryAdvertisement? = withContext(Dispatchers.IO) {
    val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
    val multicastLock = wifiManager?.createMulticastLock("pps-companion-discovery")?.apply {
        setReferenceCounted(false)
        runCatching { acquire() }
    }
    try {
        val deadline = System.currentTimeMillis() + timeoutMs.coerceAtLeast(250)
        val buffer = ByteArray(8192)
        MulticastSocket(null).use { socket ->
            socket.reuseAddress = true
            socket.soTimeout = 250
            socket.bind(InetSocketAddress(COMPANION_DISCOVERY_PORT))
            val group = InetAddress.getByName(COMPANION_DISCOVERY_MULTICAST_GROUP)
            runCatching { socket.joinGroup(group) }
            while (System.currentTimeMillis() < deadline) {
                val packet = DatagramPacket(buffer, buffer.size)
                val raw = runCatching {
                    socket.receive(packet)
                    String(packet.data, packet.offset, packet.length, StandardCharsets.UTF_8)
                }.getOrNull() ?: continue
                CompanionDiscoveryAdvertisement.parseOrNull(raw)?.let { return@withContext it }
            }
        }
        null
    } finally {
        runCatching { multicastLock?.release() }
    }
}

private fun urlEncode(value: String): String =
    URLEncoder.encode(value, StandardCharsets.UTF_8.name())
