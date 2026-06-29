package io.ppskit.runnercompanion

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.SystemClock
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.RandomAccessFile
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToLong

internal data class PhonePcmWavInfo(
    val formatTag: Int,
    val sampleRateHz: Int,
    val channelCount: Int,
    val bitsPerSample: Int,
    val blockAlignBytes: Int,
    val dataOffsetBytes: Long,
    val dataSizeBytes: Long,
) {
    val bytesPerFrame: Int = blockAlignBytes.takeIf { it > 0 } ?: ((channelCount * bitsPerSample) / 8)
    val frameCount: Long = if (bytesPerFrame > 0) dataSizeBytes / bytesPerFrame else 0L
    val durationMs: Long = if (sampleRateHz > 0) ((frameCount * 1000.0) / sampleRateHz).roundToLong() else 0L
    val audioTrackEncoding: Int
        get() = when {
            formatTag == WAVE_FORMAT_PCM && bitsPerSample == 8 -> AudioFormat.ENCODING_PCM_8BIT
            formatTag == WAVE_FORMAT_PCM && bitsPerSample == 16 -> AudioFormat.ENCODING_PCM_16BIT
            formatTag == WAVE_FORMAT_PCM && bitsPerSample == 24 -> AudioFormat.ENCODING_PCM_24BIT_PACKED
            formatTag == WAVE_FORMAT_PCM && bitsPerSample == 32 -> AudioFormat.ENCODING_PCM_32BIT
            else -> throw IllegalArgumentException("Unsupported phone WAV encoding: format=$formatTag bits=$bitsPerSample")
        }
    val encodingLabel: String
        get() = when {
            formatTag == WAVE_FORMAT_PCM -> "pcm_${bitsPerSample}bit"
            else -> "format_${formatTag}_${bitsPerSample}bit"
        }
}

internal data class PhoneAudioCueDelivery(
    val scheduledAudioFrame: Long,
    val playbackHeadFrame: Long,
    val deliveryElapsedRealtimeMs: Long,
    val jitterFrames: Long,
    val jitterMs: Double,
)

private const val WAVE_FORMAT_PCM = 1

internal fun readPhonePcmWavInfo(file: File): PhonePcmWavInfo {
    RandomAccessFile(file, "r").use { wav ->
        require(wav.length() >= 44L) { "WAV file is too small: ${file.name}" }
        require(wav.readFourCc() == "RIFF") { "Expected RIFF WAV header in ${file.name}" }
        wav.readUInt32Le()
        require(wav.readFourCc() == "WAVE") { "Expected WAVE file type in ${file.name}" }

        var formatTag = 0
        var channelCount = 0
        var sampleRateHz = 0
        var blockAlignBytes = 0
        var bitsPerSample = 0
        var dataOffsetBytes = -1L
        var dataSizeBytes = 0L

        while (wav.filePointer + 8L <= wav.length()) {
            val chunkId = wav.readFourCc()
            val chunkSize = wav.readUInt32Le()
            val chunkDataOffset = wav.filePointer
            when (chunkId) {
                "fmt " -> {
                    require(chunkSize >= 16L) { "Invalid fmt chunk in ${file.name}" }
                    formatTag = wav.readUInt16Le()
                    channelCount = wav.readUInt16Le()
                    sampleRateHz = wav.readUInt32Le().toInt()
                    wav.readUInt32Le()
                    blockAlignBytes = wav.readUInt16Le()
                    bitsPerSample = wav.readUInt16Le()
                }
                "data" -> {
                    dataOffsetBytes = chunkDataOffset
                    dataSizeBytes = chunkSize
                }
            }
            wav.seek(chunkDataOffset + chunkSize + (chunkSize % 2L))
            if (formatTag != 0 && dataOffsetBytes >= 0L) break
        }

        require(formatTag == WAVE_FORMAT_PCM) { "Only PCM WAV block audio is supported on phone runtime; found format $formatTag in ${file.name}" }
        require(channelCount in 1..8) { "Unsupported phone WAV channel count $channelCount in ${file.name}" }
        require(sampleRateHz > 0) { "Missing sample rate in ${file.name}" }
        require(bitsPerSample in setOf(8, 16, 24, 32)) { "Unsupported PCM bit depth $bitsPerSample in ${file.name}" }
        require(blockAlignBytes > 0) { "Missing block alignment in ${file.name}" }
        require(dataOffsetBytes >= 0L && dataSizeBytes > 0L) { "Missing data chunk in ${file.name}" }
        require(dataSizeBytes % blockAlignBytes == 0L) { "WAV data size is not frame-aligned in ${file.name}" }
        return PhonePcmWavInfo(
            formatTag = formatTag,
            sampleRateHz = sampleRateHz,
            channelCount = channelCount,
            bitsPerSample = bitsPerSample,
            blockAlignBytes = blockAlignBytes,
            dataOffsetBytes = dataOffsetBytes,
            dataSizeBytes = dataSizeBytes,
        )
    }
}

internal suspend fun playBlockAudioWithAudioTrack(
    file: File,
    wavInfo: PhonePcmWavInfo,
    cues: List<MobileCue>,
    onCue: suspend (MobileCue, PhoneAudioCueDelivery) -> Unit,
    onProgress: suspend (Long, Long) -> Unit,
) = withContext(Dispatchers.IO) {
    val audioTrack = buildPhoneAudioTrack(wavInfo)
    try {
        audioTrack.play()
        coroutineScope {
            val cueJob = launch {
                deliverCuesFromAudioTrack(audioTrack, wavInfo, cues, onCue)
            }
            streamPcmWavData(file, wavInfo, audioTrack, onProgress)
            cueJob.join()
            waitForPlaybackDrain(audioTrack, wavInfo, onProgress)
        }
    } finally {
        runCatching { audioTrack.pause() }
        runCatching { audioTrack.flush() }
        runCatching { audioTrack.release() }
    }
}

private fun buildPhoneAudioTrack(wavInfo: PhonePcmWavInfo): AudioTrack {
    val encoding = wavInfo.audioTrackEncoding
    val format = AudioFormat.Builder()
        .setSampleRate(wavInfo.sampleRateHz)
        .setEncoding(encoding)
        .apply {
            when (wavInfo.channelCount) {
                1 -> setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                2 -> setChannelMask(AudioFormat.CHANNEL_OUT_STEREO)
                else -> setChannelIndexMask((1 shl wavInfo.channelCount) - 1)
            }
        }
        .build()
    val minBuffer = if (wavInfo.channelCount <= 2) {
        AudioTrack.getMinBufferSize(
            wavInfo.sampleRateHz,
            if (wavInfo.channelCount == 1) AudioFormat.CHANNEL_OUT_MONO else AudioFormat.CHANNEL_OUT_STEREO,
            encoding,
        ).coerceAtLeast(0)
    } else {
        0
    }
    val quarterSecond = (wavInfo.sampleRateHz / 4).coerceAtLeast(1) * wavInfo.bytesPerFrame
    val bufferSize = max(4096, max(minBuffer, quarterSecond))
    val track = AudioTrack.Builder()
        .setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build(),
        )
        .setAudioFormat(format)
        .setTransferMode(AudioTrack.MODE_STREAM)
        .setBufferSizeInBytes(bufferSize)
        .build()
    require(track.state == AudioTrack.STATE_INITIALIZED) { "AudioTrack failed to initialize for phone WAV playback." }
    return track
}

private suspend fun streamPcmWavData(
    file: File,
    wavInfo: PhonePcmWavInfo,
    audioTrack: AudioTrack,
    onProgress: suspend (Long, Long) -> Unit,
) {
    val buffer = ByteArray(max(4096, wavInfo.bytesPerFrame * 2048))
    var remaining = wavInfo.dataSizeBytes
    var lastProgressMs = 0L
    RandomAccessFile(file, "r").use { wav ->
        wav.seek(wavInfo.dataOffsetBytes)
        while (remaining > 0L && currentCoroutineContext().isActive) {
            val read = wav.read(buffer, 0, min(buffer.size.toLong(), remaining).toInt())
            if (read <= 0) break
            var written = 0
            while (written < read && currentCoroutineContext().isActive) {
                val count = audioTrack.write(buffer, written, read - written, AudioTrack.WRITE_BLOCKING)
                if (count < 0) throw IllegalStateException("AudioTrack write failed with code $count")
                written += count
            }
            remaining -= read.toLong()
            val now = SystemClock.elapsedRealtime()
            if (now - lastProgressMs >= 100L) {
                emitAudioTrackProgress(audioTrack, wavInfo, onProgress)
                lastProgressMs = now
            }
        }
    }
}

private suspend fun deliverCuesFromAudioTrack(
    audioTrack: AudioTrack,
    wavInfo: PhonePcmWavInfo,
    cues: List<MobileCue>,
    onCue: suspend (MobileCue, PhoneAudioCueDelivery) -> Unit,
) {
    val scheduled = cues
        .map { cue -> cue to min((cue.timeS.coerceAtLeast(0.0) * wavInfo.sampleRateHz).roundToLong(), wavInfo.frameCount) }
        .sortedBy { it.second }
    for ((cue, scheduledFrame) in scheduled) {
        while (currentCoroutineContext().isActive) {
            val headFrame = playbackHeadFrame(audioTrack)
            if (headFrame >= scheduledFrame) {
                val jitterFrames = headFrame - scheduledFrame
                onCue(
                    cue,
                    PhoneAudioCueDelivery(
                        scheduledAudioFrame = scheduledFrame,
                        playbackHeadFrame = headFrame,
                        deliveryElapsedRealtimeMs = SystemClock.elapsedRealtime(),
                        jitterFrames = jitterFrames,
                        jitterMs = jitterFrames * 1000.0 / wavInfo.sampleRateHz,
                    ),
                )
                break
            }
            val framesUntilCue = scheduledFrame - headFrame
            val delayMs = (framesUntilCue * 1000L / wavInfo.sampleRateHz).coerceIn(1L, 20L)
            delay(delayMs)
        }
    }
}

private suspend fun waitForPlaybackDrain(
    audioTrack: AudioTrack,
    wavInfo: PhonePcmWavInfo,
    onProgress: suspend (Long, Long) -> Unit,
) {
    while (currentCoroutineContext().isActive && playbackHeadFrame(audioTrack) < wavInfo.frameCount) {
        emitAudioTrackProgress(audioTrack, wavInfo, onProgress)
        delay(100L)
    }
    onProgress(wavInfo.durationMs, wavInfo.durationMs)
}

private suspend fun emitAudioTrackProgress(
    audioTrack: AudioTrack,
    wavInfo: PhonePcmWavInfo,
    onProgress: suspend (Long, Long) -> Unit,
) {
    val elapsedFrames = playbackHeadFrame(audioTrack).coerceIn(0L, wavInfo.frameCount)
    onProgress((elapsedFrames * 1000.0 / wavInfo.sampleRateHz).roundToLong(), wavInfo.durationMs)
}

private fun playbackHeadFrame(audioTrack: AudioTrack): Long =
    audioTrack.playbackHeadPosition.toLong() and 0xFFFF_FFFFL

private fun RandomAccessFile.readFourCc(): String {
    val bytes = ByteArray(4)
    readFully(bytes)
    return bytes.toString(Charsets.US_ASCII)
}

private fun RandomAccessFile.readUInt16Le(): Int {
    val b0 = read()
    val b1 = read()
    require(b0 >= 0 && b1 >= 0) { "Unexpected end of WAV header." }
    return b0 or (b1 shl 8)
}

private fun RandomAccessFile.readUInt32Le(): Long {
    val b0 = read()
    val b1 = read()
    val b2 = read()
    val b3 = read()
    require(b0 >= 0 && b1 >= 0 && b2 >= 0 && b3 >= 0) { "Unexpected end of WAV header." }
    return (b0.toLong() or (b1.toLong() shl 8) or (b2.toLong() shl 16) or (b3.toLong() shl 24)) and 0xFFFF_FFFFL
}
