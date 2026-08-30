package io.ppskit.questrunner.core

import org.junit.Assert.assertEquals
import org.junit.Test

class JniRunnerCoreTest {
  @Test
  fun `every Kotlin operation invokes exactly one matching native binding`() {
    val bindings = RecordingBindings()
    val core = JniRunnerCore(bindings)

    assertEquals(RunnerState.READY, core.requestSnapshot().state)
    assertEquals(RunnerState.READY, core.armTarget().state)
    assertEquals(RunnerState.READY, core.disarmTarget().state)
    assertEquals(RunnerState.RUNNING, core.startDemo().state)
    assertEquals(RunnerState.PAUSED, core.pause().state)
    assertEquals(RunnerState.RUNNING, core.resume().state)
    assertEquals(RunnerState.STOPPED, core.stop().state)

    assertEquals(
        listOf(
            "request_snapshot",
            "arm_target",
            "disarm_target",
            "start_demo",
            "pause",
            "resume",
            "stop",
        ),
        bindings.calls,
    )
  }

  private class RecordingBindings : NativeCommandBindings {
    val calls = mutableListOf<String>()
    private var revision = 0L

    override fun requestSnapshotJson(): String = response("request_snapshot", "ready")

    override fun startDemoJson(): String = response("start_demo", "running")

    override fun armTargetJson(): String = response("arm_target", "ready", armed = true)

    override fun disarmTargetJson(): String = response("disarm_target", "ready")

    override fun pauseJson(): String = response("pause", "paused")

    override fun resumeJson(): String = response("resume", "running")

    override fun stopJson(): String = response("stop", "stopped")

    private fun response(command: String, state: String, armed: Boolean = false): String {
      calls += command
      return """{"schema":"$RUNNER_SNAPSHOT_SCHEMA","state":"$state","revision":${revision++},"message":"ok","core":"fake-native","armed":$armed,"connection_state":"local_only"}"""
    }
  }
}
