package io.ppskit.runnercompanion

import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.roundToInt

data class TimelineTick(
    val seconds: Double,
    val label: String,
)

data class TimelineDensityStyle(
    val markerScale: Float,
    val drawCueClickConnectors: Boolean,
)

object TimelineLayoutModel {
    private val tickStepsS = listOf(
        1.0, 2.0, 5.0, 10.0, 15.0, 30.0,
        60.0, 120.0, 180.0, 300.0, 600.0, 900.0,
    )

    fun resolveDuration(vararg values: Double): Double =
        values
            .filter { it.isFinite() && it > 0.0 }
            .maxOrNull()
            ?.coerceAtLeast(1.0)
            ?: 1.0

    fun ticks(durationS: Double, plotWidthPx: Float, minSpacingPx: Float = 92f): List<TimelineTick> {
        val duration = resolveDuration(durationS)
        val availableTicks = ((plotWidthPx / minSpacingPx).toInt() + 1).coerceAtLeast(2)
        val rawStep = duration / (availableTicks - 1).coerceAtLeast(1)
        val step = tickStepsS.firstOrNull { it >= rawStep } ?: niceLargeStep(rawStep)
        val ticks = mutableListOf(0.0)
        var current = step
        while (current < duration) {
            ticks += current
            current += step
        }
        if (ticks.last() < duration) {
            ticks += duration
        }
        return ticks.distinctBy { (it * 1000.0).roundToInt() }.map { TimelineTick(it, formatTime(it)) }
    }

    fun formatTime(seconds: Double): String {
        val totalSeconds = seconds.coerceAtLeast(0.0)
        if (totalSeconds < 60.0) {
            val rounded = totalSeconds.roundToInt()
            return if (kotlin.math.abs(totalSeconds - rounded) < 0.05) {
                "${rounded}s"
            } else {
                String.format("%.1fs", totalSeconds)
            }
        }
        val rounded = totalSeconds.toInt()
        val hours = rounded / 3600
        val minutes = (rounded % 3600) / 60
        val secondsPart = rounded % 60
        return if (hours > 0) {
            "%d:%02d:%02d".format(hours, minutes, secondsPart)
        } else {
            "%d:%02d".format(minutes, secondsPart)
        }
    }

    fun shouldShowTrialLabel(
        startS: Double,
        endS: Double,
        durationS: Double,
        plotWidthPx: Float,
        minWidthPx: Float = 78f,
    ): Boolean {
        val duration = resolveDuration(durationS)
        val start = startS.coerceIn(0.0, duration)
        val end = endS.coerceIn(start, duration)
        val width = ((end - start) / duration) * plotWidthPx
        return width >= minWidthPx
    }

    fun densityStyle(eventCount: Int, plotWidthPx: Float, minSpacingPx: Float = 7f): TimelineDensityStyle {
        if (eventCount <= 0) {
            return TimelineDensityStyle(markerScale = 1f, drawCueClickConnectors = true)
        }
        val spacing = plotWidthPx / eventCount.coerceAtLeast(1)
        return when {
            spacing < minSpacingPx * 0.55f -> TimelineDensityStyle(markerScale = 0.45f, drawCueClickConnectors = false)
            spacing < minSpacingPx -> TimelineDensityStyle(markerScale = 0.65f, drawCueClickConnectors = false)
            spacing < minSpacingPx * 1.8f -> TimelineDensityStyle(markerScale = 0.8f, drawCueClickConnectors = true)
            else -> TimelineDensityStyle(markerScale = 1f, drawCueClickConnectors = true)
        }
    }

    private fun niceLargeStep(rawStep: Double): Double {
        if (!rawStep.isFinite() || rawStep <= 0.0) return 60.0
        val minutes = rawStep / 60.0
        val magnitude = Math.pow(10.0, floor(kotlin.math.log10(minutes.coerceAtLeast(1.0))))
        val normalized = minutes / magnitude
        val nice = when {
            normalized <= 1.0 -> 1.0
            normalized <= 2.0 -> 2.0
            normalized <= 5.0 -> 5.0
            else -> 10.0
        }
        return ceil(nice * magnitude) * 60.0
    }
}
