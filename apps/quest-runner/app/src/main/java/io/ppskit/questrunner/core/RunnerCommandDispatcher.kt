package io.ppskit.questrunner.core

enum class RunnerCommand(val wireValue: String) {
  REQUEST_SNAPSHOT("request_snapshot"),
  START_DEMO("start_demo"),
  ARM_TARGET("arm_target"),
  DISARM_TARGET("disarm_target"),
  PAUSE("pause"),
  RESUME("resume"),
  STOP("stop"),
}

/** Shared semantic ingress for local Spatial UI now and a future BRSP adapter. */
class RunnerCommandDispatcher(
    private val core: RunnerCore,
) {
  fun dispatch(command: RunnerCommand): RunnerSnapshot =
      when (command) {
        RunnerCommand.REQUEST_SNAPSHOT -> core.requestSnapshot()
        RunnerCommand.START_DEMO -> core.startDemo()
        RunnerCommand.ARM_TARGET -> core.armTarget()
        RunnerCommand.DISARM_TARGET -> core.disarmTarget()
        RunnerCommand.PAUSE -> core.pause()
        RunnerCommand.RESUME -> core.resume()
        RunnerCommand.STOP -> core.stop()
      }
}
