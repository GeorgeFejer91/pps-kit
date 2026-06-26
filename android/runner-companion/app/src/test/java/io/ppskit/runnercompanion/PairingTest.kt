package io.ppskit.runnercompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PairingTest {
    @Test
    fun parsesPairingUri() {
        val pairing = PairingInfo.parse(
            "pps-companion://pair?v=1&host=192.168.1.20&port=8767&session_id=session-1&token=abc123",
        )

        assertEquals("192.168.1.20", pairing.host)
        assertEquals(8767, pairing.port)
        assertEquals("session-1", pairing.sessionId)
        assertEquals("abc123", pairing.token)
        assertEquals("http://192.168.1.20:8767", pairing.baseHttpUrl)
        assertEquals("ws://192.168.1.20:8767/api/runner/ws", pairing.wsUrl)
    }

    @Test
    fun rejectsMissingToken() {
        assertNull(
            PairingInfo.parseOrNull("pps-companion://pair?v=1&host=192.168.1.20&port=8767&session_id=session-1"),
        )
    }
}
