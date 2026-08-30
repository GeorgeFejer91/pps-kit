package io.ppskit.questrunner.core

import org.junit.Assert.assertEquals
import org.junit.Test

class RunnerCommandDispatcherTest {
  @Test
  fun `typed dispatcher maps the complete preview command set`() {
    val core = RecordingCore()
    val dispatcher = RunnerCommandDispatcher(core)

    RunnerCommand.entries.forEach(dispatcher::dispatch)

    assertEquals(RunnerCommand.entries, core.calls)
  }

  private class RecordingCore : RunnerCore {
    val calls = mutableListOf<RunnerCommand>()
    private val snapshot =
        RunnerSnapshot(RunnerState.READY, 0L, "ok", "fake", false, "local_only")

    override fun requestSnapshot(): RunnerSnapshot = record(RunnerCommand.REQUEST_SNAPSHOT)

    override fun startDemo(): RunnerSnapshot = record(RunnerCommand.START_DEMO)

    override fun armTarget(): RunnerSnapshot = record(RunnerCommand.ARM_TARGET)

    override fun disarmTarget(): RunnerSnapshot = record(RunnerCommand.DISARM_TARGET)

    override fun pause(): RunnerSnapshot = record(RunnerCommand.PAUSE)

    override fun resume(): RunnerSnapshot = record(RunnerCommand.RESUME)

    override fun stop(): RunnerSnapshot = record(RunnerCommand.STOP)

    private fun record(command: RunnerCommand): RunnerSnapshot {
      calls += command
      return snapshot
    }
  }
}
