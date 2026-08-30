package io.ppskit.questrunner

import io.ppskit.questrunner.core.JniBindings
import io.ppskit.questrunner.core.MAX_BRSP_CONTROL_BYTES
import io.ppskit.questrunner.core.MAX_BRSP_RELAY_QUEUE_BYTES
import io.ppskit.questrunner.core.MAX_BRSP_STATE_BYTES
import io.ppskit.questrunner.core.NativeRelayBindings
import io.ppskit.questrunner.core.NativeRelayResultCodec
import io.ppskit.questrunner.core.RelayPairing
import io.ppskit.questrunner.core.RelayPairingCodec
import java.net.URI
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONObject

internal const val BRSP_POLL_INTERVAL_MILLIS = 250L

private val relayErrorCodePattern = Regex("^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
private val nonFatalRelayErrors = setOf("peer_absent", "peer_disconnected")

internal enum class RelayPhase {
  DISCONNECTED,
  CONFIGURED,
  CONNECTING,
  WAITING_CONTROLLER,
  AUTHENTICATING,
  READY,
  ERROR,
}

internal data class RelayUiState(
    val phase: RelayPhase = RelayPhase.DISCONNECTED,
    val message: String = "Remote networking is inert until Generate and Connect are pressed.",
    val pairing: RelayPairing? = null,
) {
  val socketActive: Boolean
    get() = phase in setOf(
        RelayPhase.CONNECTING,
        RelayPhase.WAITING_CONTROLLER,
        RelayPhase.AUTHENTICATING,
        RelayPhase.READY,
    )
}

internal data class RelayEndpoint(
    val baseUrl: String,
    val room: String,
    val socketUrl: String,
    val companionBaseUrl: String,
) {
  companion object {
    private val roomPattern = Regex("^[A-Za-z0-9_-]{8,64}$")

    fun parse(baseUrl: String, room: String, allowCleartext: Boolean): RelayEndpoint {
      val trimmedBase = baseUrl.trim().trimEnd('/')
      require(trimmedBase.length <= 512) { "Relay base URL is too long." }
      require(roomPattern.matches(room)) { "Room must match [A-Za-z0-9_-]{8,64}." }
      val uri = runCatching { URI(trimmedBase) }.getOrElse { throw IllegalArgumentException("Relay base URL is invalid.") }
      require(uri.scheme == "ws" || uri.scheme == "wss") { "Relay base must use ws:// or wss://." }
      require(uri.host != null && uri.rawAuthority != null) { "Relay base must include a host." }
      require(uri.userInfo == null && uri.query == null && uri.fragment == null) {
        "Relay base cannot contain credentials, query, or fragment."
      }
      require(uri.rawPath.isNullOrEmpty() || uri.rawPath == "/") {
        "Relay base must not contain a path; the app owns the relay route."
      }
      require(uri.scheme == "wss" || allowCleartext) {
        "Release builds require a wss:// relay."
      }
      val authority = uri.rawAuthority
      val normalizedBase = "${uri.scheme}://$authority"
      val webScheme = if (uri.scheme == "wss") "https" else "http"
      return RelayEndpoint(
          baseUrl = normalizedBase,
          room = room,
          socketUrl = "$normalizedBase/ws/relay/$room/target",
          companionBaseUrl = "$webScheme://$authority/companion/",
      )
    }
  }
}

internal sealed interface RelayMetadata {
  data class Peer(val role: String, val present: Boolean) : RelayMetadata

  data class Error(val code: String, val message: String) : RelayMetadata
}

internal object RelayMetadataCodec {
  fun decodeIfRelay(frame: String): RelayMetadata? {
    val payload = JSONObject(frame)
    return when (payload.optString("kind")) {
      "relay.peer" -> {
        require(payload.namesSet() == setOf("kind", "role", "present")) {
          "relay.peer fields are invalid."
        }
        val role = payload.getString("role")
        require(role == "target" || role == "controller") { "relay.peer role is invalid." }
        require(payload.get("present") is Boolean) { "relay.peer present must be boolean." }
        RelayMetadata.Peer(role, payload.getBoolean("present"))
      }
      "relay.error" -> {
        require(payload.namesSet() == setOf("kind", "code", "message")) {
          "relay.error fields are invalid."
        }
        val code = payload.getString("code")
        val message = payload.getString("message")
        require(relayErrorCodePattern.matches(code)) { "relay.error code is invalid." }
        require(message.toByteArray(Charsets.UTF_8).size <= 256) {
          "relay.error message is too long."
        }
        RelayMetadata.Error(code, message)
      }
      else -> null
    }
  }
}

internal fun requireRelayQueueCapacity(queuedBytes: Long, outbound: List<String>) {
  require(queuedBytes in 0..MAX_BRSP_RELAY_QUEUE_BYTES) {
    "Relay reliable queue already exceeds 256 KiB."
  }
  val offeredBytes = outbound.sumOf { it.toByteArray(Charsets.UTF_8).size.toLong() }
  require(offeredBytes <= MAX_BRSP_RELAY_QUEUE_BYTES - queuedBytes) {
    "Relay reliable queue would exceed 256 KiB."
  }
}

internal data class RelayOutboundBatch(
    val control: List<String>,
    val newestState: String?,
)

/** Keep reliable control ordered, but retain only the newest replaceable state frame. */
internal fun coalesceRelayOutbound(
    outbound: List<String>,
    pendingState: String? = null,
): RelayOutboundBatch {
  val control = mutableListOf<String>()
  var newestState = pendingState
  outbound.forEach { frame ->
    if (JSONObject(frame).optString("type") == "state") {
      require(frame.toByteArray(Charsets.UTF_8).size <= MAX_BRSP_STATE_BYTES) {
        "Native BRSP state frame exceeds 8 KiB."
      }
      newestState = frame
    } else {
      control += frame
    }
  }
  return RelayOutboundBatch(control, newestState)
}

internal fun <T : Any> isCurrentNativeRelaySession(
    activeSocket: T?,
    callbackSocket: T,
    nativeSessionActive: Boolean,
): Boolean = nativeSessionActive && activeSocket === callbackSocket

/**
 * Opt-in LAN relay transport. It understands only relay metadata and the JNI result envelope;
 * BRSP authentication, scopes, sequencing, leases, action eligibility, and dispatch stay in Rust.
 */
internal class RelayTargetController(
    private val enabled: Boolean,
    private val allowCleartext: Boolean,
    private val onSnapshotChanged: () -> Unit,
    private val native: NativeRelayBindings? = if (enabled) JniBindings else null,
    private val client: OkHttpClient = OkHttpClient(),
    private val pollIntervalMillis: Long = BRSP_POLL_INTERVAL_MILLIS,
    private val closeClientOnShutdown: Boolean = true,
) {
  init {
    require(pollIntervalMillis in 1..1_000) { "Relay poll interval is invalid." }
  }

  internal val available: Boolean = enabled && native?.available == true

  private val mutableState =
      MutableStateFlow(
          when {
            !enabled ->
                RelayUiState(
                    phase = RelayPhase.DISCONNECTED,
                    message = "Remote disabled by this APK's build configuration.",
                )
            !available ->
                RelayUiState(
                    phase = RelayPhase.DISCONNECTED,
                    message =
                        "Remote unavailable: the Rust JNI core is not packaged (${native?.unavailableReason ?: "native bindings unavailable"}).",
                )
            else -> RelayUiState()
          },
      )
  val state: StateFlow<RelayUiState> = mutableState.asStateFlow()

  private val pollExecutor =
      Executors.newSingleThreadScheduledExecutor { runnable ->
        Thread(runnable, "pps-quest-brsp-poll").apply { isDaemon = true }
      }
  private var pollFuture: ScheduledFuture<*>? = null
  private var socket: WebSocket? = null
  private var endpoint: RelayEndpoint? = null
  private var pairing: RelayPairing? = null
  private var controllerPresent = false
  private var nativeSessionActive = false
  private var pendingStateFrame: String? = null
  private var shutdown = false

  @Synchronized
  fun generatePairing(baseUrl: String, room: String) {
    require(available) { "Remote is unavailable because the Rust JNI core is not packaged." }
    require(!shutdown) { "Relay controller is shut down." }
    require(socket == null) { "Disconnect before rotating pairing material." }
    val nextEndpoint = RelayEndpoint.parse(baseUrl, room.trim(), allowCleartext)
    require(pairing?.room != nextEndpoint.room) {
      "Rotating pairing material requires a fresh relay room."
    }
    val nextPairing =
        RelayPairingCodec.decode(
            nativeAuthority().createPairingJson(nextEndpoint.companionBaseUrl, nextEndpoint.room),
        )
    endpoint = nextEndpoint
    pairing = nextPairing
    mutableState.value =
        RelayUiState(
            phase = RelayPhase.CONFIGURED,
            message = "Invitation generated locally. Press Connect to opt into the relay.",
            pairing = nextPairing,
        )
  }

  @Synchronized
  fun connect(baseUrl: String, room: String) {
    require(available) { "Remote is unavailable because the Rust JNI core is not packaged." }
    require(!shutdown) { "Relay controller is shut down." }
    require(socket == null) { "Relay socket is already active." }
    val selected = RelayEndpoint.parse(baseUrl, room.trim(), allowCleartext)
    val configuredEndpoint = requireNotNull(endpoint) { "Generate an invitation before connecting." }
    val configuredPairing = requireNotNull(pairing) { "Generate an invitation before connecting." }
    require(selected == configuredEndpoint) {
      "Relay base or room changed; generate a fresh invitation before connecting."
    }
    controllerPresent = false
    pendingStateFrame = null
    mutableState.value =
        RelayUiState(RelayPhase.CONNECTING, "Opening the explicit relay connection…", configuredPairing)
    val request = Request.Builder().url(selected.socketUrl).build()
    try {
      socket = client.newWebSocket(request, SessionListener())
    } catch (error: RuntimeException) {
      mutableState.value =
          RelayUiState(
              RelayPhase.ERROR,
              "Relay start failed: ${error.message ?: error::class.java.simpleName}",
              pairing,
          )
      throw error
    }
  }

  @Synchronized
  fun disconnect() {
    terminateSocket(
        expectedSocket = null,
        reason = "Disconnected by the local Quest operator.",
        finalPhase = RelayPhase.DISCONNECTED,
        closeCode = 1000,
        closeReason = "local disconnect",
    )
  }

  @Synchronized
  fun shutdown() {
    if (shutdown) return
    shutdown = true
    terminateSocket(
        expectedSocket = null,
        reason = "Quest Activity closed.",
        finalPhase = RelayPhase.DISCONNECTED,
        closeCode = 1000,
        closeReason = "activity closed",
    )
    pollExecutor.shutdownNow()
    if (closeClientOnShutdown) {
      client.dispatcher.executorService.shutdown()
      client.connectionPool.evictAll()
    }
  }

  @Synchronized
  fun onHostPaused() {
    if (enabled && socket != null) {
      terminateSocket(
          expectedSocket = null,
          reason = "Quest Activity paused; remote authority was revoked.",
          finalPhase = RelayPhase.DISCONNECTED,
          closeCode = 1000,
          closeReason = "activity paused",
      )
    }
  }

  @Synchronized
  private fun terminateSocket(
      expectedSocket: WebSocket?,
      reason: String,
      finalPhase: RelayPhase,
      closeCode: Int?,
      closeReason: String,
  ) {
    if (expectedSocket != null && socket !== expectedSocket) return
    pollFuture?.cancel(false)
    pollFuture = null
    controllerPresent = false
    pendingStateFrame = null
    val active = socket
    socket = null
    val cleanupMessage = endNativeSession(reason)
    mutableState.value =
        RelayUiState(
            finalPhase,
            cleanupMessage?.let { "$reason Native cleanup failed: $it" } ?: reason,
            pairing,
        )
    if (closeCode != null) active?.close(closeCode, closeReason.take(123))
  }

  @Synchronized
  private fun endNativeSession(reason: String): String? {
    if (!nativeSessionActive) return null
    nativeSessionActive = false
    val failure =
        runCatching {
              val result = NativeRelayResultCodec.decode(nativeAuthority().endRelayJson(reason))
              if (result.refreshUi) onSnapshotChanged()
            }
            .exceptionOrNull()
    return failure?.message ?: failure?.javaClass?.simpleName
  }

  private inner class SessionListener : WebSocketListener() {
    override fun onOpen(webSocket: WebSocket, response: Response) {
      synchronized(this@RelayTargetController) {
        if (socket !== webSocket) return
        mutableState.value =
            RelayUiState(
                RelayPhase.WAITING_CONTROLLER,
                "Relay open; waiting for one controller peer. No BRSP hello is buffered.",
                pairing,
            )
        pollFuture =
            pollExecutor.scheduleWithFixedDelay(
                { poll(webSocket) },
                pollIntervalMillis,
                pollIntervalMillis,
                TimeUnit.MILLISECONDS,
            )
      }
    }

    override fun onMessage(webSocket: WebSocket, text: String) {
      if (text.toByteArray(Charsets.UTF_8).size > MAX_BRSP_CONTROL_BYTES) {
        fail(webSocket, "Relay frame exceeds 16 KiB.")
        return
      }
      try {
        when (val metadata = RelayMetadataCodec.decodeIfRelay(text)) {
          is RelayMetadata.Peer -> handlePeer(webSocket, metadata)
          is RelayMetadata.Error -> handleRelayError(webSocket, metadata)
          null -> handleApplicationFrame(webSocket, text)
        }
      } catch (error: RuntimeException) {
        fail(webSocket, error.message ?: "Relay frame handling failed.")
      }
    }

    override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
      fail(webSocket, "Binary relay frames are not supported.")
    }

    override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
      synchronized(this@RelayTargetController) {
        if (socket === webSocket) {
          terminateSocket(
              expectedSocket = webSocket,
              reason = "Relay closed ($code): $reason",
              finalPhase = RelayPhase.DISCONNECTED,
              closeCode = null,
              closeReason = "",
          )
        }
      }
    }

    override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
      synchronized(this@RelayTargetController) {
        if (socket === webSocket) {
          terminateSocket(
              expectedSocket = webSocket,
              reason = "Relay failed: ${t.message ?: t::class.java.simpleName}",
              finalPhase = RelayPhase.ERROR,
              closeCode = null,
              closeReason = "",
          )
        }
      }
    }
  }

  @Synchronized
  private fun handleApplicationFrame(webSocket: WebSocket, text: String) {
    // Callback delivery may race a close/reconnect. Fence the socket and
    // native-session generation before evaluating the JNI call itself.
    if (!isCurrentNativeRelaySession(socket, webSocket, nativeSessionActive)) return
    processNative(webSocket, nativeAuthority().handleRelayFrameJson(text))
  }

  @Synchronized
  private fun handlePeer(webSocket: WebSocket, peer: RelayMetadata.Peer) {
    if (socket !== webSocket || peer.role != "controller") return
    if (peer.present && !controllerPresent) {
      controllerPresent = true
      pendingStateFrame = null
      val configuredPairing = requireNotNull(pairing)
      nativeSessionActive = true
      try {
        processNative(webSocket, nativeAuthority().beginRelayJson(configuredPairing.secret))
      } catch (error: RuntimeException) {
        fail(webSocket, error.message ?: "Native BRSP session start failed.")
      }
    } else if (!peer.present && controllerPresent) {
      handleControllerAbsent("Controller left; lease invalidated. The next peer must re-handshake.")
    }
  }

  @Synchronized
  private fun handleRelayError(webSocket: WebSocket, error: RelayMetadata.Error) {
    if (socket !== webSocket) return
    if (error.code in nonFatalRelayErrors) {
      handleControllerAbsent(
          when (error.code) {
            "peer_absent" -> "Relay is waiting for a controller; no BRSP authority is active."
            else -> "Controller disconnected; lease invalidated. A fresh handshake is required."
          },
      )
      return
    }
    fail(webSocket, "Relay ${error.code}: ${error.message}")
  }

  @Synchronized
  private fun handleControllerAbsent(message: String) {
    controllerPresent = false
    pendingStateFrame = null
    val cleanupError = endNativeSession("Controller left the relay; fresh proof required.")
    if (cleanupError != null) {
      terminateSocket(
          expectedSocket = socket,
          reason = "$message Native cleanup failed: $cleanupError",
          finalPhase = RelayPhase.ERROR,
          closeCode = 1011,
          closeReason = "native cleanup failed",
      )
      return
    }
    mutableState.value =
        RelayUiState(
            RelayPhase.WAITING_CONTROLLER,
            message,
            pairing,
        )
  }

  @Synchronized
  private fun poll(webSocket: WebSocket) {
    if (socket !== webSocket || !nativeSessionActive) return
    val phase = mutableState.value.phase
    if (phase != RelayPhase.AUTHENTICATING && phase != RelayPhase.READY) return
    runCatching { processNative(webSocket, nativeAuthority().pollRelayJson()) }
        .onFailure { fail(webSocket, it.message ?: "Native relay poll failed.") }
  }

  @Synchronized
  private fun processNative(webSocket: WebSocket, encodedResult: String) {
    if (socket !== webSocket) return
    val result = NativeRelayResultCodec.decode(encodedResult)
    val batch = coalesceRelayOutbound(result.outbound, pendingStateFrame)
    pendingStateFrame = batch.newestState
    requireRelayQueueCapacity(webSocket.queueSize(), batch.control)
    batch.control.forEach { frame ->
      if (!webSocket.send(frame)) throw IllegalStateException("Relay rejected an outbound frame.")
    }
    if (result.refreshUi) onSnapshotChanged()
    val phase =
        when (result.phase) {
          "authenticating" -> RelayPhase.AUTHENTICATING
          "ready" -> RelayPhase.READY
          "error", "lease_expired" -> RelayPhase.ERROR
          else -> mutableState.value.phase
        }
    mutableState.value = RelayUiState(phase, result.message, pairing)
    if (result.close || phase == RelayPhase.ERROR) {
      terminateSocket(
          expectedSocket = webSocket,
          reason = result.message,
          finalPhase = if (phase == RelayPhase.ERROR) RelayPhase.ERROR else RelayPhase.DISCONNECTED,
          closeCode = 1002,
          closeReason = "BRSP session closed",
      )
    } else {
      flushPendingState(webSocket)
    }
  }

  private fun flushPendingState(webSocket: WebSocket) {
    if (socket !== webSocket || webSocket.queueSize() != 0L) return
    val newest = pendingStateFrame ?: return
    pendingStateFrame = null
    if (!webSocket.send(newest)) {
      pendingStateFrame = newest
      throw IllegalStateException("Relay rejected the newest state frame.")
    }
  }

  @Synchronized
  private fun fail(webSocket: WebSocket, message: String) {
    if (socket !== webSocket) return
    terminateSocket(
        expectedSocket = webSocket,
        reason = message,
        finalPhase = RelayPhase.ERROR,
        closeCode = 1002,
        closeReason = "relay protocol failure",
    )
  }

  private fun nativeAuthority(): NativeRelayBindings =
      requireNotNull(native?.takeIf { available && it.available }) {
        "Canonical BRSP/1 native authority is unavailable."
      }
}

private fun JSONObject.namesSet(): Set<String> = buildSet {
  val iterator = keys()
  while (iterator.hasNext()) add(iterator.next())
}
