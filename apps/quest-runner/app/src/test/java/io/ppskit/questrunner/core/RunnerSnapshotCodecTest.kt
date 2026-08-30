package io.ppskit.questrunner.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class RunnerSnapshotCodecTest {
  @Test
  fun `strict snapshot parses the supported schema`() {
    val snapshot =
        RunnerSnapshotCodec.decode(
            """{"schema":"$RUNNER_SNAPSHOT_SCHEMA","state":"paused","revision":7,"message":"waiting","core":"rust-jni-preview","armed":true,"connection_state":"relay_ready"}""",
        )

    assertEquals(RunnerState.PAUSED, snapshot.state)
    assertEquals(7L, snapshot.revision)
    assertEquals("waiting", snapshot.message)
    assertEquals(true, snapshot.armed)
    assertEquals("relay_ready", snapshot.connectionState)
  }

  @Test
  fun `unknown fields are rejected`() {
    assertThrows(IllegalArgumentException::class.java) {
      RunnerSnapshotCodec.decode(
          """{"schema":"$RUNNER_SNAPSHOT_SCHEMA","state":"ready","revision":0,"message":"ok","core":"rust","armed":false,"connection_state":"local_only","unexpected":true}""",
      )
    }
  }

  @Test
  fun `negative revision is rejected`() {
    assertThrows(IllegalArgumentException::class.java) {
      RunnerSnapshotCodec.decode(
          """{"schema":"$RUNNER_SNAPSHOT_SCHEMA","state":"ready","revision":-1,"message":"ok","core":"rust","armed":false,"connection_state":"local_only"}""",
      )
    }
  }

  @Test
  fun `unknown state is rejected`() {
    assertThrows(IllegalArgumentException::class.java) {
      RunnerSnapshotCodec.decode(
          """{"schema":"$RUNNER_SNAPSHOT_SCHEMA","state":"teleporting","revision":0,"message":"ok","core":"rust","armed":false,"connection_state":"local_only"}""",
      )
    }
  }
}
