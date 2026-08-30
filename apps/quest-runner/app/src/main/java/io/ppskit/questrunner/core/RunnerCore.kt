package io.ppskit.questrunner.core

const val RUNNER_SNAPSHOT_SCHEMA = "pps-quest-runner-snapshot.v1"

enum class RunnerState(val wireValue: String) {
  READY("ready"),
  RUNNING("running"),
  PAUSED("paused"),
  STOPPED("stopped"),
  ERROR("error");

  companion object {
    fun fromWireValue(value: String): RunnerState =
        entries.firstOrNull { it.wireValue == value }
            ?: throw IllegalArgumentException("Unsupported runner state: $value")
  }
}

data class RunnerSnapshot(
    val state: RunnerState,
    val revision: Long,
    val message: String,
    val core: String,
    val armed: Boolean,
    val connectionState: String,
)

interface RunnerCore {
  fun requestSnapshot(): RunnerSnapshot

  fun startDemo(): RunnerSnapshot

  fun armTarget(): RunnerSnapshot

  fun disarmTarget(): RunnerSnapshot

  fun pause(): RunnerSnapshot

  fun resume(): RunnerSnapshot

  fun stop(): RunnerSnapshot
}
