package io.ppskit.runnercompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PhoneHapticCalibrationTest {
    @Test
    fun ascendingCalibrationStopsAtFirstFeltAmplitude() {
        val session = PhoneHapticCalibrationSession.start(
            hasVibrator = true,
            hasAmplitudeControl = true,
            levelsPercent = listOf(5, 10, 20),
        )

        val first = session.record(felt = false)
        assertNull(first.result)
        assertEquals(10, first.session.currentThresholdPercent)

        val second = first.session.record(felt = true)
        val result = second.result ?: error("Expected calibration result")

        assertEquals("threshold_detected", result.status)
        assertEquals(10, result.recommendedThresholdPercent)
        assertEquals(phoneHapticAmplitudeFromPercent(10.0, hasAmplitudeControl = true), result.recommendedAmplitude)
        assertEquals(2, result.responses.size)
        assertTrue(result.toJson().getJSONArray("responses").getJSONObject(1).getBoolean("felt"))
    }

    @Test
    fun calibrationReportsNotDetectedAtMax() {
        val result = PhoneHapticCalibrationSession.start(
            hasVibrator = true,
            hasAmplitudeControl = true,
            levelsPercent = listOf(5, 10),
        ).record(felt = false).session.record(felt = false).result ?: error("Expected max result")

        assertEquals("not_detected_at_max", result.status)
        assertEquals(10, result.recommendedThresholdPercent)
        assertEquals(2, result.responses.size)
    }

    @Test
    fun binaryVibratorUsesDefaultAmplitude() {
        val result = PhoneHapticCalibrationSession.start(
            hasVibrator = true,
            hasAmplitudeControl = false,
        ).record(felt = true).result ?: error("Expected binary result")

        assertEquals("binary_detected", result.status)
        assertEquals(100, result.recommendedThresholdPercent)
        assertEquals(PHONE_HAPTIC_DEFAULT_AMPLITUDE, result.recommendedAmplitude)
    }

    @Test
    fun amplitudeMappingClampsPercentRange() {
        assertEquals(3, phoneHapticAmplitudeFromPercent(0.1, hasAmplitudeControl = true))
        assertEquals(128, phoneHapticAmplitudeFromPercent(50.0, hasAmplitudeControl = true))
        assertEquals(255, phoneHapticAmplitudeFromPercent(200.0, hasAmplitudeControl = true))
        assertEquals(PHONE_HAPTIC_DEFAULT_AMPLITUDE, phoneHapticAmplitudeFromPercent(50.0, hasAmplitudeControl = false))
    }
}
