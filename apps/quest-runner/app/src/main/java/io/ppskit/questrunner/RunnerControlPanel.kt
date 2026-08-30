package io.ppskit.questrunner

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.ppskit.questrunner.core.RunnerCommand
import io.ppskit.questrunner.core.RunnerState
import java.security.SecureRandom
import java.util.Base64

private val RelayRoomRandom = SecureRandom()

internal fun freshRelayRoom(): String {
  val random = ByteArray(12)
  RelayRoomRandom.nextBytes(random)
  return "quest_${Base64.getUrlEncoder().withoutPadding().encodeToString(random)}"
}

private val PanelColors =
    darkColorScheme(
        primary = Color(0xFF67D7FF),
        secondary = Color(0xFFB6F09C),
        surface = Color(0xF21B2430),
        onSurface = Color(0xFFF2F7FA),
    )

@Composable
internal fun RunnerControlPanel(
    controller: RunnerPanelController,
    relayController: RelayTargetController,
    allowCleartext: Boolean,
    remoteEnabled: Boolean,
) {
  val snapshot by controller.snapshot.collectAsState()
  val relay by relayController.state.collectAsState()
  var relayBase by remember {
    mutableStateOf(if (allowCleartext) "ws://192.168.1.10:8788" else "wss://relay.example")
  }
  var room by remember { mutableStateOf(freshRelayRoom()) }
  var localError by remember { mutableStateOf("") }

  fun locally(block: () -> Unit) {
    localError = runCatching(block).exceptionOrNull()?.message.orEmpty()
  }

  MaterialTheme(colorScheme = PanelColors) {
    Surface(
        modifier = Modifier.fillMaxSize(),
        shape = RoundedCornerShape(28.dp),
        tonalElevation = 8.dp,
    ) {
      Column(
          modifier =
              Modifier.fillMaxSize()
                  .verticalScroll(rememberScrollState())
                  .padding(horizontal = 38.dp, vertical = 30.dp),
          verticalArrangement = Arrangement.spacedBy(16.dp),
      ) {
        Text(
            text = "PPS Quest Runner",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
        )
        Text(
            text =
                if (remoteEnabled) {
                  "Native Spatial SDK preview · shared Rust authority · BRSP/1 relay target"
                } else {
                  "Native Spatial SDK preview · shared Rust authority · remote fail-closed"
                },
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.72f),
        )

        Column(
            modifier =
                Modifier.fillMaxWidth()
                    .background(
                        color = stateColor(snapshot.state).copy(alpha = 0.14f),
                        shape = RoundedCornerShape(18.dp),
                    )
                    .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(7.dp),
        ) {
          Row(
              modifier = Modifier.fillMaxWidth(),
              horizontalArrangement = Arrangement.SpaceBetween,
              verticalAlignment = Alignment.CenterVertically,
          ) {
            Text(
                text = snapshot.state.wireValue.uppercase(),
                color = stateColor(snapshot.state),
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleLarge,
            )
            Text("revision ${snapshot.revision}")
          }
          Text(snapshot.message)
          Text(
              text =
                  "local arm: ${if (snapshot.armed) "ARMED" else "disarmed"} · ${snapshot.connectionState} · ${snapshot.core}",
              style = MaterialTheme.typography.labelLarge,
              color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.66f),
          )
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
          OutlinedButton(
              onClick = { controller.dispatch(RunnerCommand.ARM_TARGET) },
              enabled =
                  !snapshot.armed &&
                      (snapshot.state == RunnerState.READY || snapshot.state == RunnerState.STOPPED),
              modifier = Modifier.weight(1f),
          ) {
            Text("Arm locally")
          }
          OutlinedButton(
              onClick = { controller.dispatch(RunnerCommand.DISARM_TARGET) },
              enabled = snapshot.armed && snapshot.state == RunnerState.READY,
              modifier = Modifier.weight(1f),
          ) {
            Text("Disarm")
          }
          Button(
              onClick = { controller.dispatch(RunnerCommand.START_DEMO) },
              enabled = snapshot.armed && snapshot.state == RunnerState.READY,
              modifier = Modifier.weight(1f),
          ) {
            Text("Start local")
          }
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
          Button(
              onClick = { controller.dispatch(RunnerCommand.PAUSE) },
              enabled = snapshot.state == RunnerState.RUNNING,
              modifier = Modifier.weight(1f),
              colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFFFC857)),
          ) {
            Text("Pause", color = Color(0xFF1B2430))
          }
          Button(
              onClick = { controller.dispatch(RunnerCommand.RESUME) },
              enabled = snapshot.state == RunnerState.PAUSED,
              modifier = Modifier.weight(1f),
          ) {
            Text("Resume")
          }
          Button(
              onClick = { controller.dispatch(RunnerCommand.STOP) },
              enabled = snapshot.state == RunnerState.RUNNING || snapshot.state == RunnerState.PAUSED,
              modifier = Modifier.weight(1f),
              colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFEF6A6A)),
          ) {
            Text("Stop")
          }
          OutlinedButton(
              onClick = controller::refresh,
              enabled = snapshot.state != RunnerState.ERROR,
              modifier = Modifier.weight(1f),
          ) {
            Text("Refresh")
          }
        }

        Text("Browser remote", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
        if (!remoteEnabled) {
          Text(
              "Unavailable in this APK: browser remote requires both build enablement and the packaged Rust JNI core. The transport controls below are inert.",
              color = Color(0xFFFFC857),
              fontWeight = FontWeight.Bold,
          )
        }
        Text(
            text =
                if (allowCleartext) {
                  "Debug build: explicit ws:// laboratory relays and wss:// are allowed."
                } else {
                  "Release build: only wss:// relays are accepted."
                },
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.68f),
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
          OutlinedTextField(
              value = relayBase,
              onValueChange = { relayBase = it },
              enabled = remoteEnabled && !relay.socketActive,
              label = { Text("Relay base (ws/wss)") },
              singleLine = true,
              modifier = Modifier.weight(2f),
          )
          OutlinedTextField(
              value = room,
              onValueChange = { room = it },
              enabled = remoteEnabled && !relay.socketActive,
              label = { Text("Room") },
              singleLine = true,
              modifier = Modifier.weight(1f),
          )
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
          OutlinedButton(
              onClick = {
                locally {
                  if (relay.pairing != null) room = freshRelayRoom()
                  relayController.generatePairing(relayBase, room)
                }
              },
              enabled = remoteEnabled && !relay.socketActive,
              modifier = Modifier.weight(1f),
          ) {
            Text(if (relay.pairing == null) "Generate invite" else "Rotate invite")
          }
          Button(
              onClick = { locally { relayController.connect(relayBase, room) } },
              enabled = remoteEnabled && relay.pairing != null && !relay.socketActive,
              modifier = Modifier.weight(1f),
          ) {
            Text("Connect")
          }
          OutlinedButton(
              onClick = relayController::disconnect,
              enabled = remoteEnabled && relay.socketActive,
              modifier = Modifier.weight(1f),
          ) {
            Text("Disconnect")
          }
          Text(
              text = relay.phase.name.replace('_', ' '),
              color = if (relay.phase == RelayPhase.ERROR) Color(0xFFEF6A6A) else Color(0xFFB6F09C),
              fontWeight = FontWeight.Bold,
              modifier = Modifier.weight(1f),
          )
        }
        Text(localError.ifEmpty { relay.message })

        relay.pairing?.let { pairing ->
          Column(
              modifier =
                  Modifier.fillMaxWidth()
                      .background(Color.White.copy(alpha = 0.06f), RoundedCornerShape(14.dp))
                      .padding(16.dp),
              verticalArrangement = Arrangement.spacedBy(6.dp),
          ) {
            Text(
                "Target ${pairing.targetId} · session ${pairing.sessionId}",
                style = MaterialTheme.typography.bodySmall,
            )
            Text("Generated secret (sensitive)", fontWeight = FontWeight.Bold)
            SelectionContainer {
              Text(pairing.secret, style = MaterialTheme.typography.bodySmall)
            }
            Text("Companion invitation (secret is after # only)", fontWeight = FontWeight.Bold)
            SelectionContainer {
              Text(
                  pairing.invitation,
                  style = MaterialTheme.typography.bodySmall,
                  maxLines = 3,
                  overflow = TextOverflow.Ellipsis,
              )
            }
            Text(
                "Scopes: ${pairing.scopes.joinToString()}",
                style = MaterialTheme.typography.bodySmall,
            )
          }
        }

        Text(
            text =
                if (remoteEnabled) {
                  "Only the closed shared-core action registry is remotely dispatchable; arming remains local. This preview has no experiment media or physical timing validation."
                } else {
                  "No remote action is dispatchable in this build. Local arming remains explicit. This preview has no experiment media or physical timing validation."
                },
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.58f),
        )
      }
    }
  }
}

private fun stateColor(state: RunnerState): Color =
    when (state) {
      RunnerState.READY -> Color(0xFF67D7FF)
      RunnerState.RUNNING -> Color(0xFF72E59A)
      RunnerState.PAUSED -> Color(0xFFFFC857)
      RunnerState.STOPPED -> Color(0xFFB8C2CC)
      RunnerState.ERROR -> Color(0xFFEF6A6A)
    }
