package io.ppskit.questrunner

import io.ppskit.questrunner.core.RunnerCommand
import io.ppskit.questrunner.core.RunnerCommandDispatcher
import io.ppskit.questrunner.core.RunnerSnapshot
import io.ppskit.questrunner.core.RunnerState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class RunnerPanelController(
    private val dispatcher: RunnerCommandDispatcher,
) {
  private val mutableSnapshot =
      MutableStateFlow(
          runCatching { dispatcher.dispatch(RunnerCommand.REQUEST_SNAPSHOT) }
              .getOrElse { errorSnapshot(it, 0L) },
      )

  val snapshot: StateFlow<RunnerSnapshot> = mutableSnapshot.asStateFlow()

  fun dispatch(command: RunnerCommand) {
    mutableSnapshot.value =
        runCatching { dispatcher.dispatch(command) }
            .getOrElse { errorSnapshot(it, mutableSnapshot.value.revision) }
  }

  fun refresh() {
    dispatch(RunnerCommand.REQUEST_SNAPSHOT)
  }

  private fun errorSnapshot(error: Throwable, revision: Long): RunnerSnapshot =
      RunnerSnapshot(
          state = RunnerState.ERROR,
          revision = revision,
          message = error.message ?: error::class.java.simpleName,
          core = "unavailable",
          armed = false,
          connectionState = "unavailable",
      )
}
