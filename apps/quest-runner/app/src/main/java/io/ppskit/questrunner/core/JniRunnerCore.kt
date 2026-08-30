package io.ppskit.questrunner.core

import org.json.JSONObject

internal interface NativeCommandBindings {
  fun requestSnapshotJson(): String

  fun startDemoJson(): String

  fun armTargetJson(): String

  fun disarmTargetJson(): String

  fun pauseJson(): String

  fun resumeJson(): String

  fun stopJson(): String
}

/** Stable JNI surface. The shared library name and method names are part of the preview contract. */
internal object JniBindings : NativeCommandBindings, NativeRelayBindings {
  private val libraryLoad: Result<Unit> by lazy(LazyThreadSafetyMode.SYNCHRONIZED) {
    runCatching { System.loadLibrary("pps_quest_core") }
  }

  override val available: Boolean
    get() = libraryLoad.isSuccess

  override val unavailableReason: String?
    get() = libraryLoad.exceptionOrNull()?.let { it.message ?: it::class.java.simpleName }

  private external fun nativeRequestSnapshot(): String

  private external fun nativeStartDemo(): String

  private external fun nativeArmTarget(): String

  private external fun nativeDisarmTarget(): String

  private external fun nativePause(): String

  private external fun nativeResume(): String

  private external fun nativeStop(): String

  private external fun nativeCreatePairing(companionBaseUrl: String, room: String): String

  private external fun nativeBeginRelay(secret: String): String

  private external fun nativeHandleRelayFrame(frame: String): String

  private external fun nativePollRelay(): String

  private external fun nativeEndRelay(reason: String): String

  override fun requestSnapshotJson(): String = withLibrary(::nativeRequestSnapshot)

  override fun startDemoJson(): String = withLibrary(::nativeStartDemo)

  override fun armTargetJson(): String = withLibrary(::nativeArmTarget)

  override fun disarmTargetJson(): String = withLibrary(::nativeDisarmTarget)

  override fun pauseJson(): String = withLibrary(::nativePause)

  override fun resumeJson(): String = withLibrary(::nativeResume)

  override fun stopJson(): String = withLibrary(::nativeStop)

  override fun createPairingJson(companionBaseUrl: String, room: String): String =
      withLibrary { nativeCreatePairing(companionBaseUrl, room) }

  override fun beginRelayJson(secret: String): String = withLibrary { nativeBeginRelay(secret) }

  override fun handleRelayFrameJson(frame: String): String =
      withLibrary { nativeHandleRelayFrame(frame) }

  override fun pollRelayJson(): String = withLibrary(::nativePollRelay)

  override fun endRelayJson(reason: String): String = withLibrary { nativeEndRelay(reason) }

  private inline fun <T> withLibrary(block: () -> T): T {
    libraryLoad.getOrThrow()
    return block()
  }
}

internal class JniRunnerCore(
    private val bindings: NativeCommandBindings,
) : RunnerCore {
  constructor() : this(JniBindings)

  override fun requestSnapshot(): RunnerSnapshot =
      RunnerSnapshotCodec.decode(bindings.requestSnapshotJson())

  override fun startDemo(): RunnerSnapshot = RunnerSnapshotCodec.decode(bindings.startDemoJson())

  override fun armTarget(): RunnerSnapshot = RunnerSnapshotCodec.decode(bindings.armTargetJson())

  override fun disarmTarget(): RunnerSnapshot = RunnerSnapshotCodec.decode(bindings.disarmTargetJson())

  override fun pause(): RunnerSnapshot = RunnerSnapshotCodec.decode(bindings.pauseJson())

  override fun resume(): RunnerSnapshot = RunnerSnapshotCodec.decode(bindings.resumeJson())

  override fun stop(): RunnerSnapshot = RunnerSnapshotCodec.decode(bindings.stopJson())
}

internal object RunnerSnapshotCodec {
  private val requiredFields =
      setOf("schema", "state", "revision", "message", "core", "armed", "connection_state")

  fun decode(json: String): RunnerSnapshot {
    require(json.toByteArray(Charsets.UTF_8).size <= 8 * 1024) {
      "Runner snapshot exceeds the 8 KiB preview boundary."
    }
    val payload = JSONObject(json)
    val actualFields = buildSet {
      val keys = payload.keys()
      while (keys.hasNext()) add(keys.next())
    }
    require(actualFields == requiredFields) {
      "Runner snapshot fields differ from the strict preview schema."
    }
    require(payload.getString("schema") == RUNNER_SNAPSHOT_SCHEMA) {
      "Unsupported runner snapshot schema."
    }

    val rawRevision = payload.get("revision")
    require(rawRevision is Number) { "Runner snapshot revision must be numeric." }
    val revision = rawRevision.toLong()
    require(revision >= 0L) { "Runner snapshot revision must be non-negative." }

    return RunnerSnapshot(
        state = RunnerState.fromWireValue(payload.getString("state")),
        revision = revision,
        message = payload.getString("message"),
        core = payload.getString("core"),
        armed = payload.getBoolean("armed"),
        connectionState = payload.getString("connection_state"),
    )
  }
}
