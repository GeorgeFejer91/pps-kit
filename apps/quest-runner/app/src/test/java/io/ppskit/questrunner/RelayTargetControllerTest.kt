package io.ppskit.questrunner

import io.ppskit.questrunner.core.NativeRelayResultCodec
import io.ppskit.questrunner.core.NativeRelayBindings
import io.ppskit.questrunner.core.RelayPairingCodec
import okhttp3.OkHttpClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class RelayTargetControllerTest {
  @Test
  fun `default relay rooms are unpredictable valid identifiers`() {
    val first = freshRelayRoom()
    val second = freshRelayRoom()

    assertTrue(Regex("^[A-Za-z0-9_-]{8,64}$").matches(first))
    assertTrue(Regex("^[A-Za-z0-9_-]{8,64}$").matches(second))
    assertFalse(first == second)
  }

  @Test
  fun `relay endpoint owns route and never places secret in socket URL`() {
    val endpoint = RelayEndpoint.parse("wss://relay.example:9443", "quest_lab_01", false)

    assertEquals(
        "wss://relay.example:9443/ws/relay/quest_lab_01/target",
        endpoint.socketUrl,
    )
    assertEquals("https://relay.example:9443/companion/", endpoint.companionBaseUrl)
    assertFalse(endpoint.socketUrl.contains("secret"))
  }

  @Test
  fun `release endpoint rejects cleartext and all query data`() {
    assertThrows(IllegalArgumentException::class.java) {
      RelayEndpoint.parse("ws://192.168.1.20:8788", "quest_lab_01", false)
    }
    assertThrows(IllegalArgumentException::class.java) {
      RelayEndpoint.parse("wss://relay.example?secret=forbidden", "quest_lab_01", false)
    }
  }

  @Test
  fun `debug endpoint may explicitly select laboratory cleartext`() {
    val endpoint = RelayEndpoint.parse("ws://192.168.1.20:8788", "quest_lab_01", true)
    assertTrue(endpoint.socketUrl.startsWith("ws://"))
  }

  @Test
  fun `pairing codec requires fragment-only exact secret`() {
    val secret = "A".repeat(43)
    val targetId = "target_abcdefgh"
    val sessionId = "session_abcdefgh"
    val fragment =
        "mode=controller&transport=relay&room=quest_lab_01&target_id=$targetId" +
            "&session_id=$sessionId&secret=$secret&scopes=session.read"
    val pairing =
        RelayPairingCodec.decode(
            """{"schema":"pps-quest-relay-pairing.v1","ok":true,"target_id":"$targetId","session_id":"$sessionId","room":"quest_lab_01","secret":"$secret","invitation":"https://relay.example/companion/#$fragment","scopes":["session.read"],"error":""}""",
        )
    assertEquals(secret, pairing.secret)
    assertEquals(sessionId, pairing.sessionId)

    assertThrows(IllegalArgumentException::class.java) {
      RelayPairingCodec.decode(
          """{"schema":"pps-quest-relay-pairing.v1","ok":true,"target_id":"$targetId","session_id":"$sessionId","room":"quest_lab_01","secret":"$secret","invitation":"https://relay.example/companion/?secret=$secret#$fragment","scopes":["session.read"],"error":""}""",
      )
    }
  }

  @Test
  fun `pairing codec rejects unknown or noncanonical scopes`() {
    val secret = "B".repeat(43)
    val prefix =
        """{"schema":"pps-quest-relay-pairing.v1","ok":true,"target_id":"target_abcdefgh","session_id":"session_abcdefgh","room":"quest_lab_01","secret":"$secret","invitation":"https://relay.example/companion/#mode=controller&transport=relay&room=quest_lab_01&target_id=target_abcdefgh&session_id=session_abcdefgh&secret=$secret&scopes="""

    assertThrows(IllegalArgumentException::class.java) {
      RelayPairingCodec.decode(
          prefix +
              "session.transport,session.read\",\"scopes\":[\"session.transport\",\"session.read\"],\"error\":\"\"}",
      )
    }
    assertThrows(IllegalArgumentException::class.java) {
      RelayPairingCodec.decode(
          prefix + "admin.all\",\"scopes\":[\"admin.all\"],\"error\":\"\"}",
      )
    }
  }

  @Test
  fun `JNI result envelope bounds every opaque outbound frame`() {
    val result =
        NativeRelayResultCodec.decode(
            """{"schema":"pps-quest-relay-result.v1","outbound":["{\"kind\":\"hello\"}"],"refresh_ui":true,"close":false,"phase":"authenticating","message":"ok"}""",
        )
    assertEquals(1, result.outbound.size)
    assertTrue(result.refreshUi)

    val oversized = "x".repeat(16 * 1024 + 1)
    assertThrows(IllegalArgumentException::class.java) {
      NativeRelayResultCodec.decode(
          """{"schema":"pps-quest-relay-result.v1","outbound":["$oversized"],"refresh_ui":false,"close":true,"phase":"error","message":"too large"}""",
      )
    }
  }

  @Test
  fun `relay metadata parser is strict and leaves application frames opaque`() {
    assertTrue(
        RelayMetadataCodec.decodeIfRelay(
            """{"kind":"relay.peer","role":"controller","present":true}""",
        ) != null,
    )
    assertEquals(null, RelayMetadataCodec.decodeIfRelay("""{"kind":"proof"}"""))
    assertEquals(
        RelayMetadata.Error("peer_absent", "waiting"),
        RelayMetadataCodec.decodeIfRelay(
            """{"kind":"relay.error","code":"peer_absent","message":"waiting"}""",
        ),
    )
    assertThrows(IllegalArgumentException::class.java) {
      RelayMetadataCodec.decodeIfRelay(
          """{"kind":"relay.peer","role":"controller","present":true,"extra":1}""",
      )
    }
    assertThrows(IllegalArgumentException::class.java) {
      RelayMetadataCodec.decodeIfRelay(
          """{"kind":"relay.error","code":"not valid","message":"bad"}""",
      )
    }
  }

  @Test
  fun `reliable relay queue is bounded before frames are offered`() {
    requireRelayQueueCapacity(256 * 1024L - 2, listOf("ok"))

    assertThrows(IllegalArgumentException::class.java) {
      requireRelayQueueCapacity(256 * 1024L - 1, listOf("no"))
    }
    assertThrows(IllegalArgumentException::class.java) {
      requireRelayQueueCapacity(256 * 1024L + 1, emptyList())
    }
  }

  @Test
  fun `state backlog keeps only C while preserving reliable control`() {
    val stateA = """{"protocol":"brsp","type":"state","sequence":1}"""
    val stateB = """{"protocol":"brsp","type":"state","sequence":2}"""
    val stateC = """{"protocol":"brsp","type":"state","sequence":3}"""
    val applied = """{"protocol":"brsp","type":"applied","sequence":9}"""

    val batch = coalesceRelayOutbound(listOf(stateB, applied, stateC), pendingState = stateA)

    assertEquals(listOf(applied), batch.control)
    assertEquals(stateC, batch.newestState)
  }

  @Test
  fun `stale socket callback cannot enter a replacement native session`() {
    val currentSocket = Any()
    val staleSocket = Any()

    assertTrue(isCurrentNativeRelaySession(currentSocket, currentSocket, true))
    assertFalse(isCurrentNativeRelaySession(currentSocket, staleSocket, true))
    assertFalse(isCurrentNativeRelaySession(currentSocket, currentSocket, false))
  }

  @Test
  fun `missing native relay is visible and pairing remains fail closed`() {
    val bindings = UnavailableRelayBindings()
    val client = OkHttpClient()
    val controller =
        RelayTargetController(
            enabled = true,
            allowCleartext = true,
            onSnapshotChanged = {},
            native = bindings,
            client = client,
            closeClientOnShutdown = false,
        )

    try {
      assertFalse(controller.available)
      assertTrue(controller.state.value.message.contains("Rust JNI core is not packaged"))
      assertThrows(IllegalArgumentException::class.java) {
        controller.generatePairing("ws://127.0.0.1:8788", "quest_lab_01")
      }
      assertEquals(0, bindings.createPairingCalls)
    } finally {
      controller.shutdown()
      client.dispatcher.executorService.shutdown()
      client.connectionPool.evictAll()
    }
  }

  @Test
  fun `default JNI relay captures a missing host library instead of crashing construction`() {
    val controller =
        RelayTargetController(
            enabled = true,
            allowCleartext = true,
            onSnapshotChanged = {},
        )

    try {
      assertFalse(controller.available)
      assertEquals(RelayPhase.DISCONNECTED, controller.state.value.phase)
      assertTrue(controller.state.value.message.contains("Remote unavailable"))
    } finally {
      controller.shutdown()
    }
  }

  private class UnavailableRelayBindings : NativeRelayBindings {
    override val available = false
    override val unavailableReason = "test fixture has no native library"
    var createPairingCalls = 0

    override fun createPairingJson(companionBaseUrl: String, room: String): String {
      createPairingCalls += 1
      error("Unavailable bindings must not be called.")
    }

    override fun beginRelayJson(secret: String): String = error("Unavailable bindings must not be called.")

    override fun handleRelayFrameJson(frame: String): String =
        error("Unavailable bindings must not be called.")

    override fun pollRelayJson(): String = error("Unavailable bindings must not be called.")

    override fun endRelayJson(reason: String): String = error("Unavailable bindings must not be called.")
  }
}
