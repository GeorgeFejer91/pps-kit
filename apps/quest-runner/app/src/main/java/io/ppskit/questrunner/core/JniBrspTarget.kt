package io.ppskit.questrunner.core

import java.net.URI
import org.json.JSONObject

internal const val PAIRING_SCHEMA = "pps-quest-relay-pairing.v1"
internal const val RELAY_RESULT_SCHEMA = "pps-quest-relay-result.v1"
internal const val MAX_BRSP_CONTROL_BYTES = 16 * 1024
internal const val MAX_BRSP_STATE_BYTES = 8 * 1024
internal const val MAX_BRSP_RELAY_QUEUE_BYTES = 256 * 1024L

private val brspToken = Regex("^[A-Za-z0-9][A-Za-z0-9_.:-]{7,95}$")
private val brspScopeToken = Regex("^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
private val pairingSecret = Regex("^[A-Za-z0-9_-]{43}$")
private val relayRoom = Regex("^[A-Za-z0-9_-]{8,64}$")
private val questRemoteScopes =
    setOf(
        "session.abort",
        "session.annotate",
        "session.prepare",
        "session.read",
        "session.transport",
    )

internal interface NativeRelayBindings {
  val available: Boolean
    get() = true

  val unavailableReason: String?
    get() = null

  fun createPairingJson(companionBaseUrl: String, room: String): String

  fun beginRelayJson(secret: String): String

  fun handleRelayFrameJson(frame: String): String

  fun pollRelayJson(): String

  fun endRelayJson(reason: String): String
}

internal data class RelayPairing(
    val targetId: String,
    val sessionId: String,
    val room: String,
    val secret: String,
    val invitation: String,
    val scopes: List<String>,
)

internal data class NativeRelayResult(
    val outbound: List<String>,
    val refreshUi: Boolean,
    val close: Boolean,
    val phase: String,
    val message: String,
)

internal object RelayPairingCodec {
  private val fields =
      setOf(
          "schema",
          "ok",
          "target_id",
          "session_id",
          "room",
          "secret",
          "invitation",
          "scopes",
          "error",
      )
  private val invitationFields =
      setOf("mode", "transport", "room", "target_id", "session_id", "secret", "scopes")

  fun decode(json: String): RelayPairing {
    require(json.toByteArray(Charsets.UTF_8).size <= MAX_BRSP_CONTROL_BYTES) {
      "Pairing response exceeds 16 KiB."
    }
    val payload = JSONObject(json)
    require(payload.fieldNames() == fields) { "Pairing response fields differ from the JNI schema." }
    require(payload.getString("schema") == PAIRING_SCHEMA) { "Unsupported pairing schema." }
    require(payload.get("ok") is Boolean) { "Pairing ok must be boolean." }
    require(payload.getBoolean("ok")) { payload.getString("error") }
    require(payload.getString("error").isEmpty()) { "Successful pairing response contains an error." }

    val scopesJson = payload.getJSONArray("scopes")
    val scopes = (0 until scopesJson.length()).map(scopesJson::getString)
    require(scopes.isNotEmpty() && scopes.size <= questRemoteScopes.size) {
      "Pairing scopes are empty or excessive."
    }
    require(scopes == scopes.distinct().sorted()) { "Pairing scopes must be unique and sorted." }
    require(scopes.all { brspScopeToken.matches(it) && it in questRemoteScopes }) {
      "Pairing contains an unsupported scope."
    }

    val targetId = payload.getString("target_id")
    val sessionId = payload.getString("session_id")
    val room = payload.getString("room")
    require(brspToken.matches(targetId)) { "Native pairing target ID is invalid." }
    require(brspToken.matches(sessionId)) { "Native pairing session ID is invalid." }
    require(relayRoom.matches(room)) { "Native pairing room is invalid." }

    val secret = payload.getString("secret")
    require(pairingSecret.matches(secret)) { "Native pairing secret is not 32-byte base64url." }
    val invitation = payload.getString("invitation")
    require(invitation.toByteArray(Charsets.UTF_8).size <= 2 * 1024) {
      "Pairing invitation is too long."
    }
    val invitationUri = runCatching { URI(invitation) }.getOrElse {
      throw IllegalArgumentException("Pairing invitation is invalid.")
    }
    require(invitationUri.scheme == "https" || invitationUri.scheme == "http") {
      "Pairing invitation must use http(s)."
    }
    require(invitationUri.host != null && invitationUri.userInfo == null && invitationUri.rawQuery == null) {
      "Pairing invitation origin is invalid."
    }
    require(invitation.substringBefore('#').contains(secret).not()) {
      "Pairing secret escaped the invitation fragment."
    }
    val invitationValues = parseInvitationFragment(invitationUri.rawFragment.orEmpty())
    require(invitationValues.keys == invitationFields) { "Pairing invitation fields are invalid." }
    require(invitationValues["mode"] == "controller") { "Pairing invitation role is invalid." }
    require(invitationValues["transport"] == "relay") { "Pairing invitation transport is invalid." }
    require(invitationValues["room"] == room) { "Pairing invitation room differs from JNI data." }
    require(invitationValues["target_id"] == targetId) {
      "Pairing invitation target differs from JNI data."
    }
    require(invitationValues["session_id"] == sessionId) {
      "Pairing invitation session differs from JNI data."
    }
    require(invitationValues["secret"] == secret) {
      "Invitation does not contain the generated fragment secret."
    }
    require(invitationValues["scopes"] == scopes.joinToString(",")) {
      "Pairing invitation scopes differ from JNI data."
    }
    return RelayPairing(
        targetId = targetId,
        sessionId = sessionId,
        room = room,
        secret = secret,
        invitation = invitation,
        scopes = scopes,
    )
  }
}

internal object NativeRelayResultCodec {
  private val fields =
      setOf("schema", "outbound", "refresh_ui", "close", "phase", "message")

  fun decode(json: String): NativeRelayResult {
    require(json.toByteArray(Charsets.UTF_8).size <= 64 * 1024) {
      "Native relay response exceeds 64 KiB."
    }
    val payload = JSONObject(json)
    require(payload.fieldNames() == fields) { "Relay result fields differ from the JNI schema." }
    require(payload.getString("schema") == RELAY_RESULT_SCHEMA) { "Unsupported relay result schema." }
    require(payload.get("refresh_ui") is Boolean) { "Relay refresh_ui must be boolean." }
    require(payload.get("close") is Boolean) { "Relay close must be boolean." }
    val framesJson = payload.getJSONArray("outbound")
    require(framesJson.length() <= 4) { "Native relay response contains too many frames." }
    val frames =
        (0 until framesJson.length()).map { index ->
          framesJson.getString(index).also { frame ->
            require(frame.toByteArray(Charsets.UTF_8).size <= MAX_BRSP_CONTROL_BYTES) {
              "Native BRSP frame exceeds 16 KiB."
            }
          }
        }
    val phase = payload.getString("phase")
    require(
        phase in
            setOf(
                "disconnected",
                "waiting_controller",
                "authenticating",
                "ready",
                "error",
                "lease_expired",
            ),
    ) {
      "Native relay phase is invalid."
    }
    val message = payload.getString("message")
    require(message.toByteArray(Charsets.UTF_8).size <= 512) { "Native relay message is too long." }
    return NativeRelayResult(
        outbound = frames,
        refreshUi = payload.getBoolean("refresh_ui"),
        close = payload.getBoolean("close"),
        phase = phase,
        message = message,
    )
  }
}

private fun parseInvitationFragment(fragment: String): Map<String, String> {
  require(fragment.isNotEmpty()) { "Pairing invitation has no fragment." }
  val result = linkedMapOf<String, String>()
  fragment.split('&').forEach { entry ->
    val separator = entry.indexOf('=')
    require(separator > 0 && separator == entry.lastIndexOf('=')) {
      "Pairing invitation fragment is malformed."
    }
    val key = entry.substring(0, separator)
    val value = entry.substring(separator + 1)
    require(key.isNotEmpty() && value.isNotEmpty() && result.put(key, value) == null) {
      "Pairing invitation fragment contains an empty or duplicate field."
    }
  }
  return result
}

private fun JSONObject.fieldNames(): Set<String> = buildSet {
  val iterator = keys()
  while (iterator.hasNext()) add(iterator.next())
}
