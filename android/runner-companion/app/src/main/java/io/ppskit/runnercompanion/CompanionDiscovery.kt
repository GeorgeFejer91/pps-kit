package io.ppskit.runnercompanion

import android.content.Context
import android.net.wifi.WifiManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.MulticastSocket
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

internal const val COMPANION_DISCOVERY_SCHEMA = "pps-runner-companion-discovery.v1"
internal const val COMPANION_DISCOVERY_MULTICAST_GROUP = "239.255.77.83"
internal const val COMPANION_DISCOVERY_PORT = 48767

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
            require(root.optString("schema") == COMPANION_DISCOVERY_SCHEMA) { "Unsupported discovery schema." }
            require(!root.has("token") && !root.has("companion_token")) { "Discovery payload must not contain a pairing token." }
            val pairing = root.optJSONObject("pairing") ?: throw IllegalArgumentException("Discovery pairing metadata is missing.")
            require(!pairing.has("token") && !pairing.has("companion_token")) { "Discovery pairing metadata must not contain a pairing token." }
            val host = pairing.optString("host").trim()
            val port = pairing.optInt("port", 0)
            val sessionId = pairing.optString("session_id").trim()
            require(host.isNotEmpty()) { "Discovery host is missing." }
            require(port in 1..65535) { "Discovery port is invalid." }
            require(sessionId.isNotEmpty()) { "Discovery session id is missing." }
            return CompanionDiscoveryAdvertisement(
                host = host,
                port = port,
                sessionId = sessionId,
                mode = pairing.optString("mode", "pc_runner").ifBlank { "pc_runner" },
                transferId = pairing.optString("transfer_id", ""),
                transport = pairing.optString("transport", "lan").ifBlank { "lan" },
                serviceName = root.optString("service_name", "PPS Runner Companion").ifBlank { "PPS Runner Companion" },
                networkScope = root.optString("network_scope", "same_lan_or_local_hotspot"),
                tokenRequired = pairing.optBoolean("token_required", true),
            )
        }

        fun parseOrNull(raw: String?): CompanionDiscoveryAdvertisement? =
            raw?.let { runCatching { parse(it) }.getOrNull() }
    }
}

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
