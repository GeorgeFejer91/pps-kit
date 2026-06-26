package io.ppskit.runnercompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TimelineLayoutModelTest {
    @Test
    fun formatsShortAndLongBlockDurationsLegibly() {
        assertEquals("17.6s", TimelineLayoutModel.formatTime(17.6))
        assertEquals("2:00", TimelineLayoutModel.formatTime(120.0))
        assertEquals("15:00", TimelineLayoutModel.formatTime(900.0))
        assertEquals("1:02:03", TimelineLayoutModel.formatTime(3723.0))
    }

    @Test
    fun choosesReadableTicksForTwoMinuteAndFifteenMinuteBlocks() {
        val twoMinuteTicks = TimelineLayoutModel.ticks(durationS = 120.0, plotWidthPx = 1080f)
        val longTicks = TimelineLayoutModel.ticks(durationS = 900.0, plotWidthPx = 1080f)

        assertEquals("0s", twoMinuteTicks.first().label)
        assertEquals("2:00", twoMinuteTicks.last().label)
        assertTrue(twoMinuteTicks.size in 5..13)
        assertEquals("0s", longTicks.first().label)
        assertEquals("15:00", longTicks.last().label)
        assertTrue(longTicks.size in 5..10)
        assertTrue(longTicks.any { it.label == "10:00" })
    }

    @Test
    fun hidesTrialLabelsWhenLongBlocksMakeTrialsTooNarrow() {
        assertTrue(
            TimelineLayoutModel.shouldShowTrialLabel(
                startS = 0.0,
                endS = 30.0,
                durationS = 120.0,
                plotWidthPx = 1080f,
            )
        )
        assertFalse(
            TimelineLayoutModel.shouldShowTrialLabel(
                startS = 0.0,
                endS = 30.0,
                durationS = 900.0,
                plotWidthPx = 1080f,
            )
        )
    }

    @Test
    fun reducesMarkerWeightAndConnectorsForDenseEventStreams() {
        val sparse = TimelineLayoutModel.densityStyle(eventCount = 24, plotWidthPx = 1080f)
        val dense = TimelineLayoutModel.densityStyle(eventCount = 360, plotWidthPx = 1080f)

        assertEquals(1f, sparse.markerScale, 0.001f)
        assertTrue(sparse.drawCueClickConnectors)
        assertTrue(dense.markerScale < sparse.markerScale)
        assertFalse(dense.drawCueClickConnectors)
    }
}
