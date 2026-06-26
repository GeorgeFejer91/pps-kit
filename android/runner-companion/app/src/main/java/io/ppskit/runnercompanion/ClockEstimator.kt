package io.ppskit.runnercompanion

data class EstimatedClock(
    val elapsedS: Double,
    val stale: Boolean,
    val cappedAtBlockEnd: Boolean,
)

object ClockEstimator {
    fun estimate(snapshot: RunnerSnapshot?, nowLocalUnixMs: Long, connected: Boolean): EstimatedClock {
        if (snapshot == null) {
            return EstimatedClock(elapsedS = 0.0, stale = true, cappedAtBlockEnd = false)
        }
        val block = snapshot.activeBlock
        var elapsed = block.elapsedS.coerceAtLeast(0.0)
        if (!connected && block.running && !block.paused && !block.instructionWaiting) {
            val deltaS = ((nowLocalUnixMs - snapshot.receivedLocalUnixMs).coerceAtLeast(0L)) / 1000.0
            elapsed += deltaS
        }
        val capped = block.durationS > 0.0 && elapsed >= block.durationS
        if (block.durationS > 0.0) {
            elapsed = elapsed.coerceAtMost(block.durationS)
        }
        return EstimatedClock(elapsedS = elapsed, stale = !connected, cappedAtBlockEnd = capped)
    }
}
