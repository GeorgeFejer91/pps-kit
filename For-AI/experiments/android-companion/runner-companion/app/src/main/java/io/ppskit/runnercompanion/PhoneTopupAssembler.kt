package io.ppskit.runnercompanion

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.OutputStream
import java.io.RandomAccessFile
import kotlin.math.roundToLong

internal data class PhoneTopupAssemblyResult(
    val wavFile: File,
    val manifestFile: File,
    val manifest: JSONObject,
    val block: MobileBlock,
)

internal data class PhoneScheduledBlockAssemblyResult(
    val wavFile: File,
    val manifestFile: File,
    val manifest: JSONObject,
    val block: MobileBlock,
)

internal fun materializePhoneTopupBlock(
    runPackage: MobileRunPackage,
    topupPlan: JSONObject,
    outputDir: File,
    assetFileForId: (String) -> File?,
): PhoneTopupAssemblyResult? {
    val plannedTrials = topupPlan.optJSONArray("trials") ?: JSONArray()
    if (plannedTrials.length() == 0) return null
    outputDir.mkdirs()

    val sources = (0 until plannedTrials.length()).map { index ->
        val row = plannedTrials.getJSONObject(index)
        val assetId = row.optString("building_block_asset_id", "")
        require(assetId.isNotBlank()) { "Top-up trial ${index + 1} is missing a building_block_asset_id." }
        val sourceFile = assetFileForId(assetId)
        require(sourceFile?.isFile == true) { "Top-up source WAV is missing for asset $assetId." }
        PhoneTopupSource(row = row, assetId = assetId, file = sourceFile, wavInfo = readPhonePcmWavInfo(sourceFile))
    }
    val reference = sources.first().wavInfo
    sources.drop(1).forEach { source ->
        require(source.wavInfo.formatTag == reference.formatTag) { "Top-up WAV format mismatch for ${source.assetId}." }
        require(source.wavInfo.sampleRateHz == reference.sampleRateHz) { "Top-up WAV sample-rate mismatch for ${source.assetId}." }
        require(source.wavInfo.channelCount == reference.channelCount) { "Top-up WAV channel-count mismatch for ${source.assetId}." }
        require(source.wavInfo.bitsPerSample == reference.bitsPerSample) { "Top-up WAV bit-depth mismatch for ${source.assetId}." }
        require(source.wavInfo.blockAlignBytes == reference.blockAlignBytes) { "Top-up WAV block-alignment mismatch for ${source.assetId}." }
    }
    val totalDataSize = sources.sumOf { it.wavInfo.dataSizeBytes }
    require(totalDataSize <= 0xFFFF_FFFFL - 36L) { "Top-up WAV is too large for RIFF WAV output." }

    val wavFile = File(outputDir, "phone_topup_block.wav")
    writeConcatenatedPcmWav(wavFile, reference, totalDataSize, sources)

    val trials = mutableListOf<MobileTrial>()
    val cues = mutableListOf<MobileCue>()
    val trialRows = JSONArray()
    var cursorFrames = 0L
    sources.forEachIndexed { index, source ->
        val startS = cursorFrames.toDouble() / reference.sampleRateHz
        val durationS = source.wavInfo.frameCount.toDouble() / reference.sampleRateHz
        val endS = startS + durationS
        val sourceTrialUid = source.row.optString("source_trial_uid", "trial-${index + 1}")
        val trialUid = "phone-topup-${index + 1}-${sourceTrialUid}"
        val tactileOnsetS = source.row.optNullableDouble("tactile_onset_s")
        val responseOnsetS = source.row.optNullableDouble("response_window_onset_s")
        trials.add(
            MobileTrial(
                trialNumber = index + 1,
                trialUid = trialUid,
                trialType = source.row.optString("trial_type", ""),
                family = source.row.optString("family", ""),
                soaMs = source.row.optString("soa_ms", ""),
                rowLabel = source.row.optString("row_label", ""),
                noiseType = source.row.optString("noise_type", ""),
                startS = startS,
                endS = endS,
                durationS = durationS,
                tactileOnsetS = tactileOnsetS,
                responseWindowOnsetS = responseOnsetS,
                buildingBlockAssetId = source.assetId,
            ),
        )
        if (tactileOnsetS != null) {
            cues.add(
                MobileCue(
                    cueId = cues.size + 1,
                    trialNumber = index + 1,
                    trialUid = trialUid,
                    timeS = startS + tactileOnsetS,
                    trialRelativeTimeS = tactileOnsetS,
                    soaMs = source.row.optString("soa_ms", ""),
                    rowLabel = source.row.optString("row_label", ""),
                    noiseType = source.row.optString("noise_type", ""),
                ),
            )
        }
        trialRows.put(
            JSONObject(source.row.toString())
                .put("topup_trial_number", index + 1)
                .put("topup_trial_uid", trialUid)
                .put("topup_start_s", startS)
                .put("topup_end_s", endS)
                .put("topup_duration_s", durationS),
        )
        cursorFrames += source.wavInfo.frameCount
    }

    val block = MobileBlock(
        blockId = "phone-topup-01",
        index = runPackage.blocks.size + 1,
        label = "Phone top-up",
        durationS = cursorFrames.toDouble() / reference.sampleRateHz,
        trialCount = trials.size,
        audioAssetId = "phone-topup-block-audio",
        trials = trials,
        tactileCues = cues,
    )
    val manifest = JSONObject()
        .put("schema", "pps-android-phone-topup-materialization.v1")
        .put("status", "materialized")
        .put("source_plan_schema", topupPlan.optString("schema", ""))
        .put("synthesis_strategy", "pcm_wav_concat_without_ffmpeg")
        .put("package_id", runPackage.packageId)
        .put("participant_id", runPackage.participantId)
        .put("wav_filename", wavFile.name)
        .put("wav_sha256", sha256File(wavFile))
        .put("sample_rate_hz", reference.sampleRateHz)
        .put("channel_count", reference.channelCount)
        .put("bits_per_sample", reference.bitsPerSample)
        .put("encoding", reference.encodingLabel)
        .put("frame_count", cursorFrames)
        .put("duration_ms", (cursorFrames * 1000.0 / reference.sampleRateHz).roundToLong())
        .put("trial_count", trials.size)
        .put("tactile_cue_count", cues.size)
        .put("trials", trialRows)
    val manifestFile = File(outputDir, "phone_topup_materialization.json")
    manifestFile.writeText(manifest.toString(2), Charsets.UTF_8)
    return PhoneTopupAssemblyResult(wavFile = wavFile, manifestFile = manifestFile, manifest = manifest, block = block)
}

internal fun materializePhoneScheduledBlock(
    runPackage: MobileRunPackage,
    block: MobileBlock,
    outputDir: File,
    assetFileForId: (String) -> File?,
): PhoneScheduledBlockAssemblyResult? {
    if (block.trials.isEmpty()) return null
    if (block.trials.any { it.buildingBlockAssetId.isBlank() }) return null
    outputDir.mkdirs()

    val sources = block.trials.sortedBy { it.startS }.map { trial ->
        val assetId = trial.buildingBlockAssetId
        val sourceFile = assetFileForId(assetId)
        require(sourceFile?.isFile == true) { "Scheduled block source WAV is missing for asset $assetId." }
        PhoneScheduledBlockSource(trial = trial, assetId = assetId, file = sourceFile, wavInfo = readPhonePcmWavInfo(sourceFile))
    }
    val reference = sources.first().wavInfo
    sources.drop(1).forEach { source ->
        require(source.wavInfo.formatTag == reference.formatTag) { "Scheduled block WAV format mismatch for ${source.assetId}." }
        require(source.wavInfo.sampleRateHz == reference.sampleRateHz) { "Scheduled block WAV sample-rate mismatch for ${source.assetId}." }
        require(source.wavInfo.channelCount == reference.channelCount) { "Scheduled block WAV channel-count mismatch for ${source.assetId}." }
        require(source.wavInfo.bitsPerSample == reference.bitsPerSample) { "Scheduled block WAV bit-depth mismatch for ${source.assetId}." }
        require(source.wavInfo.blockAlignBytes == reference.blockAlignBytes) { "Scheduled block WAV block-alignment mismatch for ${source.assetId}." }
    }
    val totalDataSize = sources.sumOf { it.wavInfo.dataSizeBytes }
    require(totalDataSize <= 0xFFFF_FFFFL - 36L) { "Scheduled block WAV is too large for RIFF WAV output." }

    val wavFile = File(outputDir, "phone_materialized_block_${block.index.toString().padStart(2, '0')}.wav")
    writeConcatenatedScheduledPcmWav(wavFile, reference, sources)

    val trials = mutableListOf<MobileTrial>()
    val cues = mutableListOf<MobileCue>()
    val trialRows = JSONArray()
    var cursorFrames = 0L
    sources.forEachIndexed { index, source ->
        val sourceTrial = source.trial
        val startS = cursorFrames.toDouble() / reference.sampleRateHz
        val durationS = source.wavInfo.frameCount.toDouble() / reference.sampleRateHz
        val endS = startS + durationS
        trials.add(
            sourceTrial.copy(
                trialNumber = index + 1,
                startS = startS,
                endS = endS,
                durationS = durationS,
            ),
        )
        val tactileOnsetS = sourceTrial.tactileOnsetS
        if (tactileOnsetS != null) {
            cues.add(
                MobileCue(
                    cueId = cues.size + 1,
                    trialNumber = index + 1,
                    trialUid = sourceTrial.trialUid,
                    timeS = startS + tactileOnsetS,
                    trialRelativeTimeS = tactileOnsetS,
                    soaMs = sourceTrial.soaMs,
                    rowLabel = sourceTrial.rowLabel,
                    noiseType = sourceTrial.noiseType,
                ),
            )
        }
        trialRows.put(
            JSONObject()
                .put("trial_number", index + 1)
                .put("trial_uid", sourceTrial.trialUid)
                .put("building_block_asset_id", source.assetId)
                .put("trial_type", sourceTrial.trialType)
                .put("family", sourceTrial.family)
                .put("soa_ms", sourceTrial.soaMs)
                .put("row_label", sourceTrial.rowLabel)
                .put("noise_type", sourceTrial.noiseType)
                .put("start_s", startS)
                .put("end_s", endS)
                .put("duration_s", durationS)
                .put("tactile_onset_s", sourceTrial.tactileOnsetS)
                .put("response_window_onset_s", sourceTrial.responseWindowOnsetS),
        )
        cursorFrames += source.wavInfo.frameCount
    }

    val materializedBlock = block.copy(
        durationS = cursorFrames.toDouble() / reference.sampleRateHz,
        trialCount = trials.size,
        audioAssetId = "phone-materialized-${block.blockId}-audio",
        trials = trials,
        tactileCues = cues,
    )
    val manifest = JSONObject()
        .put("schema", "pps-android-phone-scheduled-block-materialization.v1")
        .put("status", "materialized")
        .put("synthesis_strategy", "pcm_wav_concat_without_ffmpeg")
        .put("package_id", runPackage.packageId)
        .put("participant_id", runPackage.participantId)
        .put("source_block_id", block.blockId)
        .put("source_block_index", block.index)
        .put("source_block_label", block.label)
        .put("wav_filename", wavFile.name)
        .put("wav_sha256", sha256File(wavFile))
        .put("sample_rate_hz", reference.sampleRateHz)
        .put("channel_count", reference.channelCount)
        .put("bits_per_sample", reference.bitsPerSample)
        .put("encoding", reference.encodingLabel)
        .put("frame_count", cursorFrames)
        .put("duration_ms", (cursorFrames * 1000.0 / reference.sampleRateHz).roundToLong())
        .put("trial_count", trials.size)
        .put("tactile_cue_count", cues.size)
        .put("trials", trialRows)
    val manifestFile = File(outputDir, "phone_materialized_block_${block.index.toString().padStart(2, '0')}.json")
    manifestFile.writeText(manifest.toString(2), Charsets.UTF_8)
    return PhoneScheduledBlockAssemblyResult(wavFile = wavFile, manifestFile = manifestFile, manifest = manifest, block = materializedBlock)
}

internal fun failedPhoneTopupMaterialization(reason: String): JSONObject =
    JSONObject()
        .put("schema", "pps-android-phone-topup-materialization.v1")
        .put("status", "failed")
        .put("synthesis_strategy", "pcm_wav_concat_without_ffmpeg")
        .put("reason", reason)

internal fun notNeededPhoneTopupMaterialization(): JSONObject =
    JSONObject()
        .put("schema", "pps-android-phone-topup-materialization.v1")
        .put("status", "not_needed")
        .put("synthesis_strategy", "pcm_wav_concat_without_ffmpeg")

private data class PhoneTopupSource(
    val row: JSONObject,
    val assetId: String,
    val file: File,
    val wavInfo: PhonePcmWavInfo,
)

private data class PhoneScheduledBlockSource(
    val trial: MobileTrial,
    val assetId: String,
    val file: File,
    val wavInfo: PhonePcmWavInfo,
)

private fun writeConcatenatedScheduledPcmWav(
    output: File,
    wavInfo: PhonePcmWavInfo,
    sources: List<PhoneScheduledBlockSource>,
) {
    val totalDataSize = sources.sumOf { it.wavInfo.dataSizeBytes }
    output.parentFile?.mkdirs()
    output.outputStream().use { out ->
        out.writeAscii("RIFF")
        out.writeUInt32Le((36L + totalDataSize).toInt())
        out.writeAscii("WAVE")
        out.writeAscii("fmt ")
        out.writeUInt32Le(16)
        out.writeUInt16Le(wavInfo.formatTag)
        out.writeUInt16Le(wavInfo.channelCount)
        out.writeUInt32Le(wavInfo.sampleRateHz)
        out.writeUInt32Le(wavInfo.sampleRateHz * wavInfo.blockAlignBytes)
        out.writeUInt16Le(wavInfo.blockAlignBytes)
        out.writeUInt16Le(wavInfo.bitsPerSample)
        out.writeAscii("data")
        out.writeUInt32Le(totalDataSize.toInt())
        sources.forEach { source -> copyWavDataChunk(source.file, source.wavInfo, out) }
    }
}

private fun writeConcatenatedPcmWav(
    output: File,
    wavInfo: PhonePcmWavInfo,
    totalDataSize: Long,
    sources: List<PhoneTopupSource>,
) {
    output.parentFile?.mkdirs()
    output.outputStream().use { out ->
        out.writeAscii("RIFF")
        out.writeUInt32Le((36L + totalDataSize).toInt())
        out.writeAscii("WAVE")
        out.writeAscii("fmt ")
        out.writeUInt32Le(16)
        out.writeUInt16Le(wavInfo.formatTag)
        out.writeUInt16Le(wavInfo.channelCount)
        out.writeUInt32Le(wavInfo.sampleRateHz)
        out.writeUInt32Le(wavInfo.sampleRateHz * wavInfo.blockAlignBytes)
        out.writeUInt16Le(wavInfo.blockAlignBytes)
        out.writeUInt16Le(wavInfo.bitsPerSample)
        out.writeAscii("data")
        out.writeUInt32Le(totalDataSize.toInt())
        sources.forEach { source -> copyWavDataChunk(source.file, source.wavInfo, out) }
    }
}

private fun copyWavDataChunk(file: File, wavInfo: PhonePcmWavInfo, output: OutputStream) {
    val buffer = ByteArray(1024 * 1024)
    var remaining = wavInfo.dataSizeBytes
    RandomAccessFile(file, "r").use { wav ->
        wav.seek(wavInfo.dataOffsetBytes)
        while (remaining > 0L) {
            val read = wav.read(buffer, 0, minOf(buffer.size.toLong(), remaining).toInt())
            if (read <= 0) break
            output.write(buffer, 0, read)
            remaining -= read.toLong()
        }
    }
}

private fun OutputStream.writeAscii(value: String) {
    write(value.toByteArray(Charsets.US_ASCII))
}

private fun OutputStream.writeUInt16Le(value: Int) {
    write(value and 0xFF)
    write((value ushr 8) and 0xFF)
}

private fun OutputStream.writeUInt32Le(value: Int) {
    write(value and 0xFF)
    write((value ushr 8) and 0xFF)
    write((value ushr 16) and 0xFF)
    write((value ushr 24) and 0xFF)
}

private fun JSONObject.optNullableDouble(key: String): Double? {
    if (!has(key) || isNull(key)) return null
    val value = optDouble(key, Double.NaN)
    return if (value.isFinite()) value.coerceAtLeast(0.0) else null
}
