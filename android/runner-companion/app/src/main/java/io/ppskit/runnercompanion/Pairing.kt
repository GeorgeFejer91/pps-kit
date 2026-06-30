package io.ppskit.runnercompanion

import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

data class PairingInfo(
    val host: String,
    val port: Int,
    val sessionId: String,
    val token: String,
    val version: Int = 1,
    val mode: String = "pc_runner",
    val transferId: String = "",
    val transport: String = "lan",
) {
    val baseHttpUrl: String
        get() = "http://$host:$port"

    val wsUrl: String
        get() = "ws://$host:$port/api/runner/ws"

    val isPhoneExport: Boolean
        get() = mode == "phone_export"

    companion object {
        fun parse(raw: String): PairingInfo {
            val uri = URI(raw.trim())
            require(uri.scheme == "pps-companion") { "Unsupported pairing scheme." }
            require(uri.host == "pair") { "Unsupported pairing host." }
            val query = parseQuery(uri.rawQuery.orEmpty())
            val host = query["host"].orEmpty().trim()
            val port = query["port"]?.toIntOrNull()
            val sessionId = query["session_id"].orEmpty().trim()
            val token = query["token"].orEmpty().trim()
            val version = query["v"]?.toIntOrNull() ?: 1
            val mode = query["mode"].orEmpty().ifBlank { "pc_runner" }.trim()
            val transferId = query["transfer_id"].orEmpty().trim()
            val transport = query["transport"].orEmpty().ifBlank { "lan" }.trim()
            require(host.isNotEmpty()) { "Pairing host is missing." }
            require(port in 1..65535) { "Pairing port is invalid." }
            require(sessionId.isNotEmpty()) { "Session id is missing." }
            require(token.isNotEmpty()) { "Pairing token is missing." }
            return PairingInfo(
                host = host,
                port = port!!,
                sessionId = sessionId,
                token = token,
                version = version,
                mode = mode,
                transferId = transferId,
                transport = transport,
            )
        }

        fun parseOrNull(raw: String?): PairingInfo? =
            raw?.let {
                runCatching { parse(it) }.getOrNull()
            }

        private fun parseQuery(rawQuery: String): Map<String, String> {
            if (rawQuery.isBlank()) return emptyMap()
            return rawQuery.split("&").mapNotNull { item ->
                val index = item.indexOf("=")
                if (index < 0) return@mapNotNull null
                val key = decode(item.substring(0, index))
                val value = decode(item.substring(index + 1))
                key to value
            }.toMap()
        }

        private fun decode(value: String): String =
            URLDecoder.decode(value, StandardCharsets.UTF_8.name())
    }
}
