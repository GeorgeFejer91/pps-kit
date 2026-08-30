package io.ppskit.questrunner

import io.ppskit.questrunner.core.NativeRelayBindings
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference
import okhttp3.OkHttpClient
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RelayTargetControllerLifecycleTest {
  @Test
  fun `peer loss is nonfatal and every begun native session ends exactly once`() {
    val server = MockWebServer()
    val relayPeer = ServerRelayPeer()
    server.enqueue(MockResponse().withWebSocketUpgrade(relayPeer))
    server.start()
    val client = OkHttpClient()
    val native = RecordingNativeRelay()
    val controller = controller(server, client, native)

    try {
      controller.generatePairing(server.wsBase(), ROOM)
      controller.connect(server.wsBase(), ROOM)
      assertTrue(relayPeer.awaitOpen())
      assertTrue(relayPeer.send(peerPresent(true)))
      assertTrue(await { native.beginCount.get() == 1 })

      // Duplicate relay presence is metadata replay, not a second BRSP authority grant.
      assertTrue(relayPeer.send(peerPresent(true)))
      assertFalse(await(timeoutMillis = 150) { native.beginCount.get() > 1 })

      assertTrue(relayPeer.send(relayError("peer_absent", "controller is gone")))
      assertTrue(await { native.endCount.get() == 1 })
      assertEquals(RelayPhase.WAITING_CONTROLLER, controller.state.value.phase)
      assertTrue(controller.state.value.socketActive)

      assertTrue(relayPeer.send(peerPresent(true)))
      assertTrue(await { native.beginCount.get() == 2 })
      controller.onHostPaused()
      assertEquals(2, native.endCount.get())
      assertEquals(RelayPhase.DISCONNECTED, controller.state.value.phase)
      assertFalse(controller.state.value.socketActive)

      controller.onHostPaused()
      controller.disconnect()
      assertEquals(2, native.endCount.get())
    } finally {
      controller.shutdown()
      client.dispatcher.executorService.shutdown()
      client.connectionPool.evictAll()
      server.shutdown()
    }
  }

  @Test
  fun `oversized frame revokes authority synchronously and reconnect starts fresh native session`() {
    val server = MockWebServer()
    val firstPeer = ServerRelayPeer()
    val secondPeer = ServerRelayPeer()
    server.enqueue(MockResponse().withWebSocketUpgrade(firstPeer))
    server.enqueue(MockResponse().withWebSocketUpgrade(secondPeer))
    server.start()
    val client = OkHttpClient()
    val native = RecordingNativeRelay()
    val controller = controller(server, client, native)

    try {
      controller.generatePairing(server.wsBase(), ROOM)
      controller.connect(server.wsBase(), ROOM)
      assertTrue(firstPeer.awaitOpen())
      assertTrue(firstPeer.send(peerPresent(true)))
      assertTrue(await { native.beginCount.get() == 1 })

      assertTrue(firstPeer.send("x".repeat(16 * 1024 + 1)))
      assertTrue(await { controller.state.value.phase == RelayPhase.ERROR })
      assertEquals(1, native.endCount.get())
      assertFalse(controller.state.value.socketActive)

      controller.connect(server.wsBase(), ROOM)
      assertTrue(secondPeer.awaitOpen())
      assertTrue(secondPeer.send(peerPresent(true)))
      assertTrue(await { native.beginCount.get() == 2 })
      controller.disconnect()
      assertEquals(2, native.endCount.get())
    } finally {
      controller.shutdown()
      client.dispatcher.executorService.shutdown()
      client.connectionPool.evictAll()
      server.shutdown()
    }
  }

  @Test
  fun `native poll owns authentication timeout and terminal cleanup`() {
    val server = MockWebServer()
    val relayPeer = ServerRelayPeer()
    server.enqueue(MockResponse().withWebSocketUpgrade(relayPeer))
    server.start()
    val client = OkHttpClient()
    val native = RecordingNativeRelay(closeOnPoll = true)
    val controller = controller(server, client, native, pollIntervalMillis = 10)

    try {
      controller.generatePairing(server.wsBase(), ROOM)
      controller.connect(server.wsBase(), ROOM)
      assertTrue(relayPeer.awaitOpen())
      assertTrue(relayPeer.send(peerPresent(true)))

      assertTrue(await { native.pollCount.get() >= 1 })
      assertTrue(await { controller.state.value.phase == RelayPhase.ERROR })
      assertEquals(1, native.endCount.get())
      assertFalse(controller.state.value.socketActive)
    } finally {
      controller.shutdown()
      client.dispatcher.executorService.shutdown()
      client.connectionPool.evictAll()
      server.shutdown()
    }
  }

  private fun controller(
      server: MockWebServer,
      client: OkHttpClient,
      native: RecordingNativeRelay,
      pollIntervalMillis: Long = BRSP_POLL_INTERVAL_MILLIS,
  ): RelayTargetController =
      RelayTargetController(
          enabled = true,
          allowCleartext = true,
          onSnapshotChanged = {},
          native = native,
          client = client,
          pollIntervalMillis = pollIntervalMillis,
          closeClientOnShutdown = false,
      )

  private class ServerRelayPeer : WebSocketListener() {
    private val open = CountDownLatch(1)
    private val socket = AtomicReference<WebSocket?>()

    override fun onOpen(webSocket: WebSocket, response: Response) {
      socket.set(webSocket)
      open.countDown()
    }

    override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
      webSocket.close(code, reason)
    }

    fun awaitOpen(): Boolean = open.await(3, TimeUnit.SECONDS)

    fun send(frame: String): Boolean = socket.get()?.send(frame) == true
  }

  private class RecordingNativeRelay(private val closeOnPoll: Boolean = false) :
      NativeRelayBindings {
    val beginCount = AtomicInteger()
    val pollCount = AtomicInteger()
    val endCount = AtomicInteger()

    override fun createPairingJson(companionBaseUrl: String, room: String): String {
      val scopes =
          listOf(
              "session.abort",
              "session.annotate",
              "session.prepare",
              "session.read",
              "session.transport",
          )
      val secret = "C".repeat(43)
      val targetId = "target_abcdefgh"
      val sessionId = "session_abcdefgh"
      val fragment =
          "mode=controller&transport=relay&room=$room&target_id=$targetId" +
              "&session_id=$sessionId&secret=$secret&scopes=${scopes.joinToString(",")}"
      return JSONObject()
          .put("schema", "pps-quest-relay-pairing.v1")
          .put("ok", true)
          .put("target_id", targetId)
          .put("session_id", sessionId)
          .put("room", room)
          .put("secret", secret)
          .put("invitation", "$companionBaseUrl#$fragment")
          .put("scopes", JSONArray(scopes))
          .put("error", "")
          .toString()
    }

    override fun beginRelayJson(secret: String): String {
      beginCount.incrementAndGet()
      return relayResult("authenticating", message = "Fresh BRSP hello sent.")
    }

    override fun handleRelayFrameJson(frame: String): String =
        relayResult("authenticating", message = "Frame accepted by native seam.")

    override fun pollRelayJson(): String {
      pollCount.incrementAndGet()
      return if (closeOnPoll) {
        relayResult(
            phase = "error",
            close = true,
            message = "BRSP authentication deadline expired.",
        )
      } else {
        relayResult("authenticating", message = "Awaiting mutual BRSP proof.")
      }
    }

    override fun endRelayJson(reason: String): String {
      endCount.incrementAndGet()
      return relayResult("disconnected", refreshUi = true, message = reason.take(128))
    }
  }

  companion object {
    private const val ROOM = "quest_lab_01"

    private fun MockWebServer.wsBase(): String =
        url("/").toString().replaceFirst("http://", "ws://").trimEnd('/')

    private fun peerPresent(present: Boolean): String =
        """{"kind":"relay.peer","role":"controller","present":$present}"""

    private fun relayError(code: String, message: String): String =
        JSONObject().put("kind", "relay.error").put("code", code).put("message", message).toString()

    private fun relayResult(
        phase: String,
        outbound: List<String> = emptyList(),
        refreshUi: Boolean = false,
        close: Boolean = false,
        message: String,
    ): String =
        JSONObject()
            .put("schema", "pps-quest-relay-result.v1")
            .put("outbound", JSONArray(outbound))
            .put("refresh_ui", refreshUi)
            .put("close", close)
            .put("phase", phase)
            .put("message", message)
            .toString()

    private fun await(timeoutMillis: Long = 3_000, condition: () -> Boolean): Boolean {
      val deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(timeoutMillis)
      while (System.nanoTime() < deadline) {
        if (condition()) return true
        Thread.sleep(10)
      }
      return condition()
    }
  }
}
