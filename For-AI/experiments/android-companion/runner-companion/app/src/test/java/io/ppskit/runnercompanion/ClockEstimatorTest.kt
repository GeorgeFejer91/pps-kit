package io.ppskit.runnercompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ClockEstimatorTest {
    @Test
    fun extrapolatesOnlyWhileDisconnectedAndRunning() {
        val snapshot = SnapshotParser.parse(sampleSnapshot(elapsedS = 3.0, durationS = 10.0), receivedLocalUnixMs = 10_000)

        val connected = ClockEstimator.estimate(snapshot, nowLocalUnixMs = 12_000, connected = true)
        val stale = ClockEstimator.estimate(snapshot, nowLocalUnixMs = 12_000, connected = false)

        assertEquals(3.0, connected.elapsedS, 0.001)
        assertFalse(connected.stale)
        assertEquals(5.0, stale.elapsedS, 0.001)
        assertTrue(stale.stale)
    }

    @Test
    fun doesNotExtrapolateWhenPausedOrInstructionWaiting() {
        val paused = SnapshotParser.parse(sampleSnapshot(paused = true, elapsedS = 3.0), receivedLocalUnixMs = 10_000)
        val waiting = SnapshotParser.parse(sampleSnapshot(waiting = true, elapsedS = 3.0), receivedLocalUnixMs = 10_000)

        assertEquals(3.0, ClockEstimator.estimate(paused, nowLocalUnixMs = 12_000, connected = false).elapsedS, 0.001)
        assertEquals(3.0, ClockEstimator.estimate(waiting, nowLocalUnixMs = 12_000, connected = false).elapsedS, 0.001)
    }

    @Test
    fun capsOfflineEstimateAtBlockEndAndResyncsOnReconnect() {
        val snapshot = SnapshotParser.parse(sampleSnapshot(elapsedS = 9.0, durationS = 10.0), receivedLocalUnixMs = 10_000)

        val offline = ClockEstimator.estimate(snapshot, nowLocalUnixMs = 15_000, connected = false)
        val resynced = ClockEstimator.estimate(snapshot, nowLocalUnixMs = 15_000, connected = true)

        assertEquals(10.0, offline.elapsedS, 0.001)
        assertTrue(offline.cappedAtBlockEnd)
        assertEquals(9.0, resynced.elapsedS, 0.001)
        assertFalse(resynced.stale)
    }
}
