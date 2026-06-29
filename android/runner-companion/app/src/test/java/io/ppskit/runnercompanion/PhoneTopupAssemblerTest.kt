package io.ppskit.runnercompanion

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.File

class PhoneTopupAssemblerTest {
    @Test
    fun materializesTopupWavByConcatenatingBuildingBlockPcmWavs() {
        val sourceA = tempWav(frameCount = 100)
        val sourceB = tempWav(frameCount = 120)
        val outputDir = File.createTempFile("pps-phone-topup", "").apply {
            delete()
            mkdirs()
        }
        val runPackage = MobilePackageParser.parseManifest(
            """
            {
              "schema": "$MOBILE_PACKAGE_SCHEMA",
              "package_id": "pkg-001",
              "participant_id": "P001",
              "session_id": "session-001",
              "mobile_runnable": true,
              "phone_owned_session": true,
              "assets": [],
              "blocks": [],
              "building_blocks": [],
              "warnings": []
            }
            """.trimIndent(),
        )
        val topupPlan = JSONObject()
            .put("schema", "pps-android-phone-topup-plan.v1")
            .put(
                "trials",
                JSONArray()
                    .put(topupTrial("source-a", "asset-a", "100", 0.020))
                    .put(topupTrial("source-b", "asset-b", "300", 0.030)),
            )

        val result = materializePhoneTopupBlock(
            runPackage = runPackage,
            topupPlan = topupPlan,
            outputDir = outputDir,
            assetFileForId = { assetId -> mapOf("asset-a" to sourceA, "asset-b" to sourceB)[assetId] },
        )

        assertNotNull(result)
        result ?: return
        assertTrue(result.wavFile.isFile)
        assertTrue(result.manifestFile.isFile)
        val info = readPhonePcmWavInfo(result.wavFile)
        assertEquals(1_000, info.sampleRateHz)
        assertEquals(220L, info.frameCount)
        assertEquals(220L, info.dataSizeBytes / info.bytesPerFrame)
        assertEquals("materialized", result.manifest.getString("status"))
        assertEquals("pcm_wav_concat_without_ffmpeg", result.manifest.getString("synthesis_strategy"))
        assertEquals(2, result.block.trials.size)
        assertEquals(0.100, result.block.trials[1].startS, 0.0001)
        assertEquals(0.020, result.block.tactileCues[0].timeS, 0.0001)
        assertEquals(0.130, result.block.tactileCues[1].timeS, 0.0001)
    }

    private fun topupTrial(sourceUid: String, assetId: String, soaMs: String, tactileOnsetS: Double): JSONObject =
        JSONObject()
            .put("source_trial_uid", sourceUid)
            .put("source_trial_number", 1)
            .put("building_block_asset_id", assetId)
            .put("trial_type", "audio_tactile")
            .put("family", "audio_tactile")
            .put("soa_ms", soaMs)
            .put("row_label", "inhale")
            .put("noise_type", "white")
            .put("duration_s", 0.1)
            .put("tactile_onset_s", tactileOnsetS)
            .put("response_window_onset_s", tactileOnsetS)

    private fun tempWav(frameCount: Int): File {
        val sampleRateHz = 1_000
        val channelCount = 1
        val bitsPerSample = 16
        val blockAlign = channelCount * bitsPerSample / 8
        val dataSize = blockAlign * frameCount
        val file = File.createTempFile("pps-phone-topup-source", ".wav")
        file.writeBytes(
            ByteArrayOutputStream().apply {
                writeAscii("RIFF")
                writeUInt32Le(36 + dataSize)
                writeAscii("WAVE")
                writeAscii("fmt ")
                writeUInt32Le(16)
                writeUInt16Le(1)
                writeUInt16Le(channelCount)
                writeUInt32Le(sampleRateHz)
                writeUInt32Le(sampleRateHz * blockAlign)
                writeUInt16Le(blockAlign)
                writeUInt16Le(bitsPerSample)
                writeAscii("data")
                writeUInt32Le(dataSize)
                write(ByteArray(dataSize))
            }.toByteArray(),
        )
        return file
    }

    private fun ByteArrayOutputStream.writeAscii(value: String) {
        write(value.toByteArray(Charsets.US_ASCII))
    }

    private fun ByteArrayOutputStream.writeUInt16Le(value: Int) {
        write(value and 0xFF)
        write((value ushr 8) and 0xFF)
    }

    private fun ByteArrayOutputStream.writeUInt32Le(value: Int) {
        write(value and 0xFF)
        write((value ushr 8) and 0xFF)
        write((value ushr 16) and 0xFF)
        write((value ushr 24) and 0xFF)
    }
}
