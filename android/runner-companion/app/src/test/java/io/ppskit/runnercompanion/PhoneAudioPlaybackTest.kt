package io.ppskit.runnercompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.File

class PhoneAudioPlaybackTest {
    @Test
    fun parsesPcmWavTimingFacts() {
        val file = tempWav(
            sampleRateHz = 44_100,
            channelCount = 2,
            bitsPerSample = 16,
            frameCount = 4_410,
        )

        val info = readPhonePcmWavInfo(file)

        assertEquals(1, info.formatTag)
        assertEquals(44_100, info.sampleRateHz)
        assertEquals(2, info.channelCount)
        assertEquals(16, info.bitsPerSample)
        assertEquals(4, info.blockAlignBytes)
        assertEquals(4_410L, info.frameCount)
        assertEquals(100L, info.durationMs)
        assertEquals("pcm_16bit", info.encodingLabel)
    }

    @Test
    fun rejectsNonPcmWavBlocks() {
        val file = tempWav(
            formatTag = 3,
            sampleRateHz = 48_000,
            channelCount = 1,
            bitsPerSample = 32,
            frameCount = 100,
        )

        assertIllegalArgument { readPhonePcmWavInfo(file) }
    }

    @Test
    fun rejectsFilesWithoutDataChunk() {
        val file = File.createTempFile("pps-phone-audio-no-data", ".wav")
        file.writeBytes(
            ByteArrayOutputStream().apply {
                writeAscii("RIFF")
                writeUInt32Le(36)
                writeAscii("WAVE")
                writeAscii("fmt ")
                writeUInt32Le(16)
                writeUInt16Le(1)
                writeUInt16Le(1)
                writeUInt32Le(44_100)
                writeUInt32Le(88_200)
                writeUInt16Le(2)
                writeUInt16Le(16)
            }.toByteArray(),
        )

        assertIllegalArgument { readPhonePcmWavInfo(file) }
    }

    @Test
    fun playbackGateTracksPauseResumeTransitions() {
        val gate = PhoneAudioPlaybackGate()

        assertFalse(gate.isPaused())
        assertTrue(gate.pause())
        assertTrue(gate.isPaused())
        assertFalse(gate.pause())
        assertTrue(gate.resume())
        assertFalse(gate.isPaused())
        assertFalse(gate.resume())
    }

    private fun tempWav(
        formatTag: Int = 1,
        sampleRateHz: Int,
        channelCount: Int,
        bitsPerSample: Int,
        frameCount: Int,
    ): File {
        val blockAlign = channelCount * bitsPerSample / 8
        val dataSize = blockAlign * frameCount
        val file = File.createTempFile("pps-phone-audio", ".wav")
        file.writeBytes(
            ByteArrayOutputStream().apply {
                writeAscii("RIFF")
                writeUInt32Le(36 + dataSize)
                writeAscii("WAVE")
                writeAscii("fmt ")
                writeUInt32Le(16)
                writeUInt16Le(formatTag)
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

    private fun assertIllegalArgument(block: () -> Unit) {
        try {
            block()
            fail("Expected IllegalArgumentException.")
        } catch (_: IllegalArgumentException) {
            // Expected.
        }
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
