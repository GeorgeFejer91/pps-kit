package io.ppskit.runnercompanion

import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

private const val TOKEN_HEADER = "X-PPS-Companion-Token"
private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()

data class SetupPayload(
    val participantCode: String,
    val participantName: String,
    val age: String,
    val handedness: String,
    val gender: String,
    val nameSharingOptIn: Boolean,
)

class RunnerClient(
    private val http: OkHttpClient = OkHttpClient(),
) {
    private data class SocketCallbacks(
        val onSnapshot: (RunnerSnapshot) -> Unit,
        val onConnection: (Boolean) -> Unit,
        val onError: (String) -> Unit,
    )

    @Volatile
    private var pairing: PairingInfo? = null
    private var webSocket: WebSocket? = null
    @Volatile
    private var socketGeneration = 0
    private var reconnectAttempt = 0
    private var reconnectFuture: ScheduledFuture<*>? = null
    private val reconnectExecutor = Executors.newSingleThreadScheduledExecutor { runnable ->
        Thread(runnable, "pps-runner-companion-reconnect").apply { isDaemon = true }
    }

    fun connect(
        pairingInfo: PairingInfo,
        onSnapshot: (RunnerSnapshot) -> Unit,
        onConnection: (Boolean) -> Unit,
        onError: (String) -> Unit,
    ) {
        close()
        pairing = pairingInfo
        socketGeneration += 1
        reconnectAttempt = 0
        openSocket(
            pairingInfo,
            SocketCallbacks(onSnapshot, onConnection, onError),
            socketGeneration,
        )
    }

    private fun openSocket(
        pairingInfo: PairingInfo,
        callbacks: SocketCallbacks,
        generation: Int,
    ) {
        cancelReconnect()
        val request = Request.Builder()
            .url(pairingInfo.wsUrl)
            .header(TOKEN_HEADER, pairingInfo.token)
            .build()
        webSocket = http.newWebSocket(
            request,
            object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    if (!isCurrent(generation)) return
                    reconnectAttempt = 0
                    callbacks.onConnection(true)
                }

                override fun onMessage(webSocket: WebSocket, text: String) {
                    if (!isCurrent(generation)) return
                    runCatching { SnapshotParser.parse(text) }
                        .onSuccess(callbacks.onSnapshot)
                        .onFailure { callbacks.onError(it.message ?: "Snapshot parse failed.") }
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    if (!isCurrent(generation)) return
                    callbacks.onConnection(false)
                    scheduleReconnect(callbacks, generation)
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    if (!isCurrent(generation)) return
                    callbacks.onConnection(false)
                    callbacks.onError(t.message ?: "WebSocket disconnected.")
                    scheduleReconnect(callbacks, generation)
                }
            },
        )
    }

    fun submitSetup(payload: SetupPayload, onSnapshot: (RunnerSnapshot) -> Unit, onError: (String) -> Unit) {
        val body = JSONObject()
            .put("participant_code", payload.participantCode)
            .put("participant_name", payload.participantName)
            .put("age", payload.age)
            .put("handedness", payload.handedness)
            .put("gender", payload.gender)
            .put("name_sharing_opt_in", payload.nameSharingOptIn)
        postSnapshot("/api/runner/setup", body, onSnapshot, onError)
    }

    fun continueInstruction(onSnapshot: (RunnerSnapshot) -> Unit, onError: (String) -> Unit) {
        postSnapshot("/api/runner/commands/continue-instruction", JSONObject(), onSnapshot, onError)
    }

    fun startPart(partNumber: Int, onSnapshot: (RunnerSnapshot) -> Unit, onError: (String) -> Unit) {
        postSnapshot("/api/runner/commands/start-part", JSONObject().put("part_number", partNumber), onSnapshot, onError)
    }

    fun pause(onSnapshot: (RunnerSnapshot) -> Unit, onError: (String) -> Unit) {
        postSnapshot("/api/runner/commands/pause", JSONObject(), onSnapshot, onError)
    }

    fun resume(onSnapshot: (RunnerSnapshot) -> Unit, onError: (String) -> Unit) {
        postSnapshot("/api/runner/commands/resume", JSONObject(), onSnapshot, onError)
    }

    fun close() {
        socketGeneration += 1
        cancelReconnect()
        pairing = null
        webSocket?.close(1000, "closed")
        webSocket = null
    }

    private fun scheduleReconnect(callbacks: SocketCallbacks, generation: Int) {
        val pairingInfo = pairing ?: return
        cancelReconnect()
        val attempt = reconnectAttempt.coerceAtMost(5)
        reconnectAttempt += 1
        val delayMs = (500L shl attempt).coerceAtMost(5_000L)
        reconnectFuture = reconnectExecutor.schedule(
            {
                if (isCurrent(generation)) {
                    openSocket(pairingInfo, callbacks, generation)
                }
            },
            delayMs,
            TimeUnit.MILLISECONDS,
        )
    }

    private fun cancelReconnect() {
        reconnectFuture?.cancel(false)
        reconnectFuture = null
    }

    private fun isCurrent(generation: Int): Boolean =
        generation == socketGeneration && pairing != null

    private fun postSnapshot(
        path: String,
        payload: JSONObject,
        onSnapshot: (RunnerSnapshot) -> Unit,
        onError: (String) -> Unit,
    ) {
        val pairingInfo = pairing
        if (pairingInfo == null) {
            onError("Phone is not paired.")
            return
        }
        val request = Request.Builder()
            .url("${pairingInfo.baseHttpUrl}$path")
            .header(TOKEN_HEADER, pairingInfo.token)
            .post(payload.toString().toRequestBody(JSON_MEDIA_TYPE))
            .build()
        http.newCall(request).enqueue(
            object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    onError(e.message ?: "Command failed.")
                }

                override fun onResponse(call: Call, response: Response) {
                    response.use {
                        val text = it.body?.string().orEmpty()
                        if (!it.isSuccessful) {
                            onError(errorMessage(text, it.code))
                            return
                        }
                        runCatching { SnapshotParser.parse(text) }
                            .onSuccess(onSnapshot)
                            .onFailure { error -> onError(error.message ?: "Snapshot parse failed.") }
                    }
                }
            },
        )
    }

    private fun errorMessage(text: String, code: Int): String {
        return runCatching {
            val detail = JSONObject(text).optJSONObject("detail")
            detail?.optString("reason")?.takeIf { it.isNotBlank() }
        }.getOrNull() ?: "Runner command failed ($code)."
    }
}
