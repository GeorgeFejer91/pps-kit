package io.ppskit.runnercompanion

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.roundToInt

internal const val PHONE_HAPTIC_CALIBRATION_SCHEMA = "pps-android-phone-haptic-calibration.v1"
internal const val PHONE_HAPTIC_DEFAULT_AMPLITUDE = -1

internal val PHONE_HAPTIC_CALIBRATION_LEVELS_PERCENT = listOf(5, 10, 15, 20, 30, 40, 55, 70, 85, 100)

internal data class PhoneHapticCalibrationResponse(
    val trialIndex: Int,
    val thresholdPercent: Int,
    val amplitude: Int,
    val felt: Boolean,
)

internal data class PhoneHapticCalibrationResult(
    val status: String,
    val hasVibrator: Boolean,
    val hasAmplitudeControl: Boolean,
    val recommendedThresholdPercent: Int?,
    val recommendedAmplitude: Int,
    val responses: List<PhoneHapticCalibrationResponse>,
) {
    fun toJson(): JSONObject =
        JSONObject()
            .put("schema", PHONE_HAPTIC_CALIBRATION_SCHEMA)
            .put("status", status)
            .put("calibration_policy", if (hasAmplitudeControl) "ascending_detection_threshold_percent" else "binary_detection_only")
            .put("has_vibrator", hasVibrator)
            .put("has_amplitude_control", hasAmplitudeControl)
            .put("recommended_threshold_percent", recommendedThresholdPercent ?: JSONObject.NULL)
            .put("recommended_amplitude", recommendedAmplitude)
            .put(
                "responses",
                JSONArray().also { array ->
                    responses.forEach { response ->
                        array.put(
                            JSONObject()
                                .put("trial_index", response.trialIndex)
                                .put("threshold_percent", response.thresholdPercent)
                                .put("amplitude", response.amplitude)
                                .put("felt", response.felt),
                        )
                    }
                },
            )
}

internal data class PhoneHapticCalibrationSession(
    val hasVibrator: Boolean,
    val hasAmplitudeControl: Boolean,
    val levelsPercent: List<Int>,
    val currentIndex: Int = 0,
    val responses: List<PhoneHapticCalibrationResponse> = emptyList(),
) {
    val currentThresholdPercent: Int
        get() = levelsPercent.getOrElse(currentIndex) { levelsPercent.lastOrNull() ?: 100 }

    val currentAmplitude: Int
        get() = phoneHapticAmplitudeFromPercent(currentThresholdPercent.toDouble(), hasAmplitudeControl)

    val isComplete: Boolean
        get() = currentIndex >= levelsPercent.size || !hasVibrator

    fun record(felt: Boolean): PhoneHapticCalibrationUpdate {
        if (!hasVibrator) {
            return PhoneHapticCalibrationUpdate(
                session = this,
                result = completeResult(
                    status = "no_vibrator",
                    recommendedThresholdPercent = null,
                    recommendedAmplitude = PHONE_HAPTIC_DEFAULT_AMPLITUDE,
                    responseRows = responses,
                ),
            )
        }
        val response = PhoneHapticCalibrationResponse(
            trialIndex = responses.size + 1,
            thresholdPercent = currentThresholdPercent,
            amplitude = currentAmplitude,
            felt = felt,
        )
        val nextResponses = responses + response
        if (felt) {
            val result = completeResult(
                status = if (hasAmplitudeControl) "threshold_detected" else "binary_detected",
                recommendedThresholdPercent = currentThresholdPercent,
                recommendedAmplitude = currentAmplitude,
                responseRows = nextResponses,
            )
            return PhoneHapticCalibrationUpdate(session = copy(responses = nextResponses), result = result)
        }
        val nextIndex = currentIndex + 1
        if (nextIndex >= levelsPercent.size) {
            val result = completeResult(
                status = "not_detected_at_max",
                recommendedThresholdPercent = levelsPercent.lastOrNull(),
                recommendedAmplitude = phoneHapticAmplitudeFromPercent((levelsPercent.lastOrNull() ?: 100).toDouble(), hasAmplitudeControl),
                responseRows = nextResponses,
            )
            return PhoneHapticCalibrationUpdate(session = copy(currentIndex = nextIndex, responses = nextResponses), result = result)
        }
        return PhoneHapticCalibrationUpdate(session = copy(currentIndex = nextIndex, responses = nextResponses), result = null)
    }

    private fun completeResult(
        status: String,
        recommendedThresholdPercent: Int?,
        recommendedAmplitude: Int,
        responseRows: List<PhoneHapticCalibrationResponse>,
    ): PhoneHapticCalibrationResult =
        PhoneHapticCalibrationResult(
            status = status,
            hasVibrator = hasVibrator,
            hasAmplitudeControl = hasAmplitudeControl,
            recommendedThresholdPercent = recommendedThresholdPercent,
            recommendedAmplitude = recommendedAmplitude,
            responses = responseRows,
        )

    companion object {
        fun start(
            hasVibrator: Boolean,
            hasAmplitudeControl: Boolean,
            levelsPercent: List<Int> = PHONE_HAPTIC_CALIBRATION_LEVELS_PERCENT,
        ): PhoneHapticCalibrationSession =
            PhoneHapticCalibrationSession(
                hasVibrator = hasVibrator,
                hasAmplitudeControl = hasAmplitudeControl,
                levelsPercent = if (hasAmplitudeControl) levelsPercent.filter { it in 1..100 }.distinct().sorted() else listOf(100),
            )
    }
}

internal data class PhoneHapticCalibrationUpdate(
    val session: PhoneHapticCalibrationSession,
    val result: PhoneHapticCalibrationResult?,
)

internal fun phoneHapticAmplitudeFromPercent(percent: Double, hasAmplitudeControl: Boolean): Int =
    if (!hasAmplitudeControl) {
        PHONE_HAPTIC_DEFAULT_AMPLITUDE
    } else {
        ((percent.coerceIn(1.0, 100.0) / 100.0) * 255.0).roundToInt().coerceIn(1, 255)
    }
