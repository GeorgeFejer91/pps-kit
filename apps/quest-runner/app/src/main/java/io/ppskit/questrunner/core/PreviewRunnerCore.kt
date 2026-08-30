package io.ppskit.questrunner.core

internal class PreviewRunnerCore(
    private val fallbackReason: String,
) : RunnerCore {
  private var state = RunnerState.READY
  private var revision = 0L
  private var message = "Kotlin preview core ready: $fallbackReason"

  @Synchronized
  override fun requestSnapshot(): RunnerSnapshot = snapshot()

  @Synchronized
  override fun startDemo(): RunnerSnapshot = transition(
      allowedFrom = setOf(RunnerState.READY, RunnerState.STOPPED),
      next = RunnerState.RUNNING,
      appliedMessage = "Demo started by Kotlin preview core.",
      command = "start_demo",
  )

  @Synchronized
  override fun armTarget(): RunnerSnapshot = snapshot(armed = true)

  @Synchronized
  override fun disarmTarget(): RunnerSnapshot = snapshot(armed = false)

  @Synchronized
  override fun pause(): RunnerSnapshot = transition(
      allowedFrom = setOf(RunnerState.RUNNING),
      next = RunnerState.PAUSED,
      appliedMessage = "Demo paused by Kotlin preview core.",
      command = "pause",
  )

  @Synchronized
  override fun resume(): RunnerSnapshot = transition(
      allowedFrom = setOf(RunnerState.PAUSED),
      next = RunnerState.RUNNING,
      appliedMessage = "Demo resumed by Kotlin preview core.",
      command = "resume",
  )

  @Synchronized
  override fun stop(): RunnerSnapshot = transition(
      allowedFrom = setOf(RunnerState.RUNNING, RunnerState.PAUSED),
      next = RunnerState.STOPPED,
      appliedMessage = "Demo stopped by Kotlin preview core.",
      command = "stop",
  )

  private fun transition(
      allowedFrom: Set<RunnerState>,
      next: RunnerState,
      appliedMessage: String,
      command: String,
  ): RunnerSnapshot {
    if (state in allowedFrom) {
      state = next
      revision += 1L
      message = appliedMessage
    } else {
      message = "$command ignored while ${state.wireValue}."
    }
    return snapshot()
  }

  private var armed = false

  private fun snapshot(armed: Boolean = this.armed): RunnerSnapshot {
    if (this.armed != armed) {
      this.armed = armed
      revision += 1L
      message = if (armed) "Target locally armed." else "Target locally disarmed."
    }
    return RunnerSnapshot(
          state = state,
          revision = revision,
          message = message,
          core = "kotlin-debug-fallback",
          armed = this.armed,
          connectionState = "local_only",
      )
  }
}

internal class UnavailableRunnerCore(error: Throwable) : RunnerCore {
  private val snapshot =
      RunnerSnapshot(
          state = RunnerState.ERROR,
          revision = 0L,
          message = "Rust JNI core unavailable: ${error.message ?: error::class.java.simpleName}",
          core = "unavailable",
          armed = false,
          connectionState = "unavailable",
      )

  override fun requestSnapshot(): RunnerSnapshot = snapshot

  override fun startDemo(): RunnerSnapshot = snapshot

  override fun armTarget(): RunnerSnapshot = snapshot

  override fun disarmTarget(): RunnerSnapshot = snapshot

  override fun pause(): RunnerSnapshot = snapshot

  override fun resume(): RunnerSnapshot = snapshot

  override fun stop(): RunnerSnapshot = snapshot
}

object RunnerCoreFactory {
  fun create(allowKotlinPreviewFallback: Boolean): RunnerCore =
      try {
        JniRunnerCore().also { it.requestSnapshot() }
      } catch (error: LinkageError) {
        if (allowKotlinPreviewFallback) {
          PreviewRunnerCore(error.message ?: error::class.java.simpleName)
        } else {
          UnavailableRunnerCore(error)
        }
      } catch (error: RuntimeException) {
        if (allowKotlinPreviewFallback) {
          PreviewRunnerCore(error.message ?: error::class.java.simpleName)
        } else {
          UnavailableRunnerCore(error)
        }
      }
}
